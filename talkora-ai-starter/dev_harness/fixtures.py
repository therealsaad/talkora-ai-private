"""SYNTHETIC TEST CONTENT ONLY. Not a textbook, rubric or student curriculum."""
from server.teaching import Card, CurriculumRef, Objective, Strategy

KEY = ("synthetic", "position-fixture", "test-only", "demo", "positions", "under", "below-relation", "v1")
FACTS = {
    "en": "Under means below something. On means touching the top. The ball is under the box.",
    "hi": "Under का अर्थ नीचे है। On का अर्थ ऊपर की सतह पर है। The ball is under the box.",
    "mr": "Under म्हणजे खाली. On म्हणजे वरच्या पृष्ठभागावर. The ball is under the box.",
}
ALTERNATE = {
    "en": "Think of the box as a little roof. The ball is below it: under.",
    "hi": "डिब्बे को छोटी छत समझो। गेंद नीचे है: under.",
    "mr": "डब्याला छोटे छप्पर समज. चेंडू खाली आहे: under.",
}
CHECKS = {
    "en": "The toy is below the cup. Which position word fits?",
    "hi": "खिलौना कप के नीचे है। कौन सा English शब्द सही जगह बताता है?",
    "mr": "खेळणे कपाच्या खाली आहे. कोणता English शब्द ही जागा सांगतो?",
}
WAIT = {"en": "Take your time. You can type when ready.",
        "hi": "आराम से सोचो। तैयार हो तो लिख सकते हो।",
        "mr": "वेळ घे. तयार झाल्यावर लिहू शकतोस."}
INDEPENDENT = {"en": "Try another example without a hint.",
               "hi": "अब बिना संकेत के नया उदाहरण सोचो।",
               "mr": "आता संकेताशिवाय नवे उदाहरण सोडव."}


def objective():
    cards = []
    for language in FACTS:
        for strategy in Strategy:
            independent = strategy in (Strategy.INDEPENDENT_CHECK, Strategy.RECALL)
            message = INDEPENDENT[language] if independent else WAIT[language] if strategy == Strategy.LISTEN else FACTS[language]
            cards.append(Card(strategy=strategy, language=language, variants=(message,),
                              question=CHECKS[language], supplies_answer=not independent and strategy != Strategy.LISTEN))
    return Objective(curriculum=CurriculumRef(namespace=KEY[0], book_id=KEY[1], edition=KEY[2], track_id=KEY[3]),
                     lesson_id=KEY[4], activity_id=KEY[5], objective_id=KEY[6], version=KEY[7],
                     grade=1, synthetic=True, review_reference="SYNTHETIC HARNESS ONLY; NOT APPROVED",
                     allowed_vocabulary=("under", "on", "ball", "box", "cup", "toy", "below", "it", "is", "the"),
                     expected_answers=("under", "it is under", "the ball is under the box"),
                     partial_terms=("below", "ball", "box"), cards=tuple(cards))
