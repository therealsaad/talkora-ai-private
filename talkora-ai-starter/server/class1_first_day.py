"""Original, school-focused voice coaching for Balbharati Grade One 1.1.

A first-day story, NOT textbook rhyme transcription. No IQ or acoustic scores.
The Node lesson engine owns all progress; Python only offers one tiny prompt.
"""
import re

SCENES = {
    'School gate': ('school', 'I am happy at school.'),
    'Skip like': ('skip', 'I can skip.'),
    'Run in': ('run', 'I can run.'),
    'Walk to': ('walk', 'I walk to school.'),
    'Give Miss Julie': ('smile', 'I can smile.'),
    'Ding dong': ('bell', 'I hear a bell.'),
    'Jump like': ('jump', 'I can jump.'),
    'Let us play': ('play', 'I can play.'),
    'Time to go': ('classroom', 'I go into my classroom.'),
    'Hooray': ('grade one', 'I am in Grade One!'),
}

# Recognise tiny, school-related questions in either spoken English or common
# Hindi/Marathi expressions. Do not pretend this is open-domain intelligence.
EXPLANATIONS = {
    'school': ('School is where we learn and play.', 'स्कूल में हम सीखते और खेलते हैं।', 'शाळेत आपण शिकतो आणि खेळतो.'),
    'skip': ('Skipping is a happy step-hop, like a bunny!', 'Skip मतलब उछलकर कदम बढ़ाना।', 'Skip म्हणजे उड्या मारत चालणे.'),
    'run': ('Running is moving fast on your feet!', 'Run मतलब पैरों से तेज़ भागना।', 'Run म्हणजे पटकन पळणे.'),
    'walk': ('Walking means taking steps slowly.', 'Walk मतलब पैदल चलना।', 'Walk म्हणजे चालणे.'),
    'smile': ('A grin is a big smile on your face!', 'Grin मतलब बड़ी सी मुस्कान।', 'Grin म्हणजे मोठं हसू.'),
    'bell': ('The school bell tells us when class begins.', 'स्कूल की घंटी बताती है कि क्लास शुरू हुई।', 'शाळेची घंटा वर्गाची वेळ सांगते.'),
    'jump': ('Jumping means pushing up from your feet!', 'Jump मतलब ऊपर उछलना।', 'Jump म्हणजे उडी मारणे.'),
    'play': ('We can play games with our friends.', 'हम दोस्तों के साथ खेल खेलते हैं।', 'आपण मित्रांसोबत खेळ खेळतो.'),
    'classroom': ('A classroom is where we learn together.', 'क्लासरूम में हम साथ पढ़ते हैं।', 'वर्गात आपण एकत्र शिकतो.'),
    'grade one': ('Grade One means your first year of primary school!', 'Grade One मतलब पहली कक्षा।', 'Grade One म्हणजे पहिली इयत्ता.'),
}

def scene_for_title(title: str):
    for marker, payload in SCENES.items():
        if marker.lower() in (title or '').lower():
            return payload
    return None


def first_day_voice_reply(language: str, title: str, question: str, transcript: str, hint_level: int) -> dict | None:
    scene = scene_for_title(title)
    if scene is None:
        return None
    target, model = scene
    speech = (transcript or '')[:400].lower().strip()
    words = ' '.join(re.findall(r'[a-z]+', speech))
    target_seen = target in words or (target == 'grade one' and 'grade 1' in speech)
    # A child may ask an ordinary related question, not just echo the teacher.
    asks = bool(re.search(r'\b(what|why|how|meaning|means|tell me|explain)\b', words)
                or re.search(r'क्या|काय|मतलब|म्हणजे|समझा|सांग|बोलो|समजत', speech))
    unsure = bool(re.search(r"don't know|not understand|help|can't|cannot", words)
                  or re.search(r'नहीं|समजत|कळत|नाही|मदद', speech))
    idx = {'en': 0, 'hi': 1, 'mr': 2}[language]
    explanation = EXPLANATIONS[target][idx]
    if asks or unsure:
        message = explanation
        follow = {'en': f'Now try with me: {model}', 'hi': f'अब मेरे साथ बोलो: {model}',
                  'mr': f'आता माझ्यासोबत म्हण: {model}'}[language]
        return dict(message=message, follow=follow, model=model, quality='UNCLEAR',
                    retry=True, action='MODEL_SENTENCE')
    if target_seen:
        message = {
            'en': 'Haha, lovely! Miss Julie nearly tripped over her dancing feet!',
            'hi': 'वाह! मिस जूली तो नाचते-नाचते गिरने वाली थीं!',
            'mr': 'वा! मिस जुली नाचता नाचता पडणार होत्या!',
        }[language]
        follow = {'en': f'Can you say: {model}', 'hi': f'अब अंग्रेज़ी में बोलो: {model}',
                  'mr': f'आता इंग्रजीत म्हण: {model}'}[language]
        return dict(message=message, follow=follow, model=model, quality='ADEQUATE',
                    retry=False, action='ASK_FOLLOW_UP')
    message = explanation if hint_level >= 1 else {
        'en': f'Let us do a funny school action together: {model}',
        'hi': f'चलो मजेदार स्कूल खेल खेलते हैं: {model}',
        'mr': f'चला मजेशीर शाळेचा खेळ खेळूया: {model}',
    }[language]
    follow = {'en': f'Can you try: {model}', 'hi': f'अंग्रेज़ी में कहो: {model}',
              'mr': f'इंग्रजीत म्हण: {model}'}[language]
    return dict(message=message, follow=follow, model=model, quality='PARTIAL',
                retry=True, action='MODEL_SENTENCE')
