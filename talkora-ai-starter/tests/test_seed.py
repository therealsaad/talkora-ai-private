import json
from pathlib import Path
root = Path(__file__).resolve().parents[1]
data = json.loads((root / 'datasets/curriculum/seed.json').read_text(encoding='utf-8'))
assert len(data) == 3
assert len({item['level_id'] for item in data}) == len(data)
assert all(item['objective'] and item['target_phrases'] for item in data)
print('Seed dataset valid')
