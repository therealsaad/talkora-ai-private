import argparse
import asyncio
import os
import re
from pathlib import Path

from app.tts.parler_service import parler_service
from app.tts.text_cleaner import clean_tts_text
from app.tts.voice_profiles import PRIYA_VOICE_ID


# These are deterministic teacher lines that appear repeatedly across lessons.
COMMON_FIXED_LINES = [
    'Wonderful!',
    'Yes! Much better!',
    'Almost there!',
    "Let's try that again.",
    'Listen carefully.',
    'Your turn.',
    'Now ask me!',
    'Tell me more.',
    'Say it as a whole sentence.',
    'What is your favourite food?',
    'What is your favourite sport?',
    'What is your favourite subject?',
    'Who do you play with?',
    'Why do you like it?',
]


def _repo_root() -> Path:
    # ai-service/app/curriculum/generate_audio.py -> talkora project root
    return Path(__file__).resolve().parents[3]


def _seed_root() -> Path:
    override = os.getenv('TALKORA_BACKEND_SEED_ROOT')
    if override:
        candidate = Path(override).expanduser().resolve()
        if candidate.exists():
            return candidate
        raise FileNotFoundError(f'TALKORA_BACKEND_SEED_ROOT does not exist: {candidate}')

    root = _repo_root()
    candidates = [
        root / 'backend' / 'src' / 'seed' / 'data',
        root / 'backend' / 'backend' / 'src' / 'seed' / 'data',
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    joined = '\n'.join(str(path) for path in candidates)
    raise FileNotFoundError(
        'Could not find Talkora backend seed data. Checked:\n' + joined
    )


def _seed_file(name: str) -> Path:
    path = _seed_root() / name
    if not path.exists():
        raise FileNotFoundError(f'Curriculum seed file not found: {path}')
    return path


def _decode_ts_string(value: str) -> str:
    # Seed text uses ordinary TypeScript string escapes. We only need the
    # small subset used in authored curriculum lines.
    return (
        value.replace("\\'", "'")
        .replace('\\"', '"')
        .replace('\\n', ' ')
        .replace('\\t', ' ')
        .replace('\\\\', '\\')
        .strip()
    )


def _quoted_values(text: str) -> list[str]:
    values: list[str] = []
    pattern = re.compile(r"'((?:\\.|[^'])*)'|\"((?:\\.|[^\"])*)\"")
    for match in pattern.finditer(text):
        raw = match.group(1) if match.group(1) is not None else match.group(2)
        values.append(_decode_ts_string(raw or ''))
    return values


def _literal_field_values(source: str, field_names: tuple[str, ...]) -> list[str]:
    names = '|'.join(re.escape(name) for name in field_names)
    pattern = re.compile(
        rf'\b(?:{names})\s*:\s*(?:\n\s*)?'
        r"(?:'((?:\\.|[^'])*)'|\"((?:\\.|[^\"])*)\")",
        flags=re.MULTILINE,
    )
    values: list[str] = []
    for match in pattern.finditer(source):
        raw = match.group(1) if match.group(1) is not None else match.group(2)
        value = clean_tts_text(_decode_ts_string(raw or ''))
        if value:
            values.append(value)
    return values


def _term_one_intros() -> list[str]:
    root = _repo_root()
    candidates = [
        root / 'backend' / 'src' / 'seed' / 'seed.ts',
        root / 'backend' / 'backend' / 'src' / 'seed' / 'seed.ts',
    ]
    for path in candidates:
        if path.exists():
            source = path.read_text(encoding='utf-8')
            # TERM_ONE_CONFIG currently has four authored intros. Restrict the
            # scan to that array to avoid unrelated strings elsewhere in seed.ts.
            start = source.find('const TERM_ONE_CONFIG')
            end = source.find('/* =========================================================\n   ACHIEVEMENTS', start)
            section = source[start:end if end != -1 else None]
            return _literal_field_values(section, ('intro',))
    return []


def _unit1_lines() -> list[str]:
    source = _seed_file('unit1FavouriteThings.ts').read_text(encoding='utf-8')

    # These fields are either spoken directly or are stable model/hint text worth
    # having in the shared cache. The regex works across the multi-line formatting
    # used by this file.
    lines = _literal_field_values(
        source,
        (
            'teacherPrompt',
            'prompt',
            'instruction',
            'modelSentence',
            'target',
            'hint',
            'ttsText',
        ),
    )
    return lines


def _compact_term1_unit_lines(unit: int) -> list[str]:
    source = _seed_file('term1Units.ts').read_text(encoding='utf-8')

    declaration = re.compile(r'export const unit(\d+)\w*Activities')
    active_unit: int | None = None
    lines: list[str] = []

    # The compact Term-1 helper calls are one activity per line. For both choice
    # and speak helpers, quoted token #3 is the teacher prompt. The penultimate
    # quoted token is the answer/target and is useful for Listen & Repeat/modeling.
    for row in source.splitlines():
        match = declaration.search(row)
        if match:
            active_unit = int(match.group(1))
            continue
        if active_unit != unit:
            continue
        if not re.match(r'\s*(?:choice|speak)\(', row):
            continue

        values = _quoted_values(row)
        if len(values) < 4:
            continue

        prompt = clean_tts_text(values[2])
        target = clean_tts_text(values[-2])
        if prompt:
            lines.append(prompt)
        if target:
            lines.append(target)

    return lines


def available_term_one_units() -> list[int]:
    source = _seed_file('term1Units.ts').read_text(encoding='utf-8')
    compact = {
        int(value)
        for value in re.findall(r'export const unit(\d+)\w*Activities', source)
    }
    return sorted({1, *compact})




def _is_speakable_fixed_line(text: str) -> bool:
    # Skip authored sentence-starter placeholders such as "My favourite food is ."
    # They are UI scaffolds, not finished teacher utterances.
    if re.search(r'\b(?:is|are|with|because|like|favourite)\s*[.]$', text, flags=re.IGNORECASE):
        return False
    if re.search(r'\b(?:is|are|with|because|like)\s*$', text, flags=re.IGNORECASE):
        return False
    return True

def fixed_lines_for_unit(unit: int) -> list[str]:
    if unit < 1 or unit > 8:
        raise ValueError('Unit must be between 1 and 8.')

    lines: list[str] = list(COMMON_FIXED_LINES)

    intros = _term_one_intros()
    if 1 <= unit <= len(intros):
        lines.insert(0, intros[unit - 1])

    if unit == 1:
        lines.extend(_unit1_lines())
    else:
        lines.extend(_compact_term1_unit_lines(unit))

    # Keep insertion order while deduplicating after the exact same TTS cleaning
    # used by the runtime cache.
    unique: list[str] = []
    seen: set[str] = set()
    for raw in lines:
        text = clean_tts_text(raw)
        identity = text.casefold()
        if not text or not _is_speakable_fixed_line(text) or identity in seen:
            continue
        seen.add(identity)
        unique.append(text)
    return unique


async def generate(units: list[int]) -> None:
    total = 0
    generated = 0
    cached = 0
    failed = 0

    for unit in units:
        lines = fixed_lines_for_unit(unit)
        print(f'unit={unit} fixed_lines={len(lines)}')
        for index, line in enumerate(lines, start=1):
            try:
                result = await parler_service.synthesize(
                    line,
                    voice=PRIYA_VOICE_ID,
                    language='en-IN',
                )
            except Exception as exc:
                total += 1
                failed += 1
                print(
                    f'unit={unit} line={index}/{len(lines)} state=FAILED '
                    f'text={line!r} error={exc}'
                )
                # Do not throw away a 100-line generation run because one
                # sampled sentence failed. Re-running later will skip all
                # successful cache entries and retry only missing lines.
                continue

            total += 1
            if result.cached:
                cached += 1
            else:
                generated += 1
            state = 'cached' if result.cached else 'generated'
            print(
                f'unit={unit} line={index}/{len(lines)} state={state} '
                f'latency_ms={result.latency_ms} hash={result.audio_hash[:12]} '
                f'path={result.path}'
            )

    print(
        'complete '
        f'lines={total} generated={generated} cached={cached} failed={failed} '
        f'units={",".join(map(str, units))}'
    )

    if failed:
        print(
            'Some phrases failed. Run the same command again: cached phrases '
            'will be skipped and only missing audio will be retried.'
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            'Generate only missing fixed Miss Julie / Priya WAVs from the '
            'existing Talkora authored curriculum.'
        )
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--unit', type=int)
    target.add_argument('--term', type=int, choices=[1])
    parser.add_argument(
        '--list-only',
        action='store_true',
        help='Print the fixed lines without loading Priya.',
    )
    args = parser.parse_args()

    units = [args.unit] if args.unit else available_term_one_units()

    if args.list_only:
        for unit in units:
            print(f'\n# Unit {unit}')
            for line in fixed_lines_for_unit(unit):
                print(line)
        return

    asyncio.run(generate(units))


if __name__ == '__main__':
    main()
