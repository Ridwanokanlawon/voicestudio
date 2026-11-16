"""Voice-safe check. Runs locally, never blocks, only warns.

Cloud voice services scan the text they are sent, not the purpose of the video.
A security-awareness script that quotes a scam word for word can look like the
scam itself. This check points at those lines so they can be reworded to
describe the attack instead of performing it."""
import re
from .textproc import sentences

SUGGEST_VOICE = ("Reword into the third person so the script describes the message "
                 "instead of speaking it, for example: 'a message claims to be from IT'. "
                 "Put the exact wording in the on-screen text instead.")
SUGGEST_STEPS = ("Say what happens, not how to do it. Keep exact keys and commands "
                 "for the on-screen visuals, for example: 'the page asks you to run a command'.")
SUGGEST_MONEY = ("Spread these words out or describe the request in the third person, "
                 "for example: 'the email asks for a rushed payment'.")

I = re.I
ATTACKER = [
    (r"\b(this is|i am|i'm|we are|we're|you are speaking (to|with)|calling from)\b[^.?!]{0,40}\b(it|i\.t\.|tech(nical)? support|help ?desk|support team|the bank|your bank|microsoft|security (team|department)|fraud (team|department))\b", "sounds like a fake support greeting"),
    (r"\b(new|updated|changed|revised)\s+(bank(ing)?|account|payment)\s+details\b", "'new bank details' wording"),
    (r"\b(urgent(ly)?|immediate(ly)?|right now|asap|within the hour|before close of business)\b[^.?!]{0,50}\b(pay(ment|ments)?|transfer|wire|invoice|settle)\b", "urgent payment request"),
    (r"\b(pay(ment)?|transfer|wire|settle)\b[^.?!]{0,50}\b(urgent(ly)?|immediate(ly)?|right now|asap)\b", "urgent payment request"),
    (r"\bgift ?cards?\b", "gift card wording"),
    (r"\b(verify|confirm|validate|update)\s+your\s+(account|identity|password|details|login|card|billing)\b", "'verify your account' wording"),
    (r"\bclick\s+(here|the link|this link|below|the button)\b", "'click here' wording"),
    (r"\byour\s+(account|mailbox|password|card)\s+(has been|will be|is being|is)\s+(suspended|locked|closed|disabled|deactivated|compromised|expir\w+)\b", "account-threat wording"),
    (r"\b(send|share|give|tell|read)\s+(me|us)\s+(your|the)\s+(password|code|otp|pin|one[- ]time)\b", "asks for a password or code"),
    (r"\b(dear (customer|user|client)|kindly (pay|send|transfer|confirm))\b", "scam-letter phrasing"),
]
THIRD_PERSON = re.compile(
    r"\b(a|an|the|this|that|one|fake|every)\s+(\w+\s+)?(message|email|e-mail|caller|call|text|attacker|scammer|criminal|"
    r"page|site|website|link|invoice|pop-?up|voice|stranger|sender|note)\b[^.?!]{0,60}\b"
    r"(claims?|asks?|says?|said|pretends?|tells?|wants?|demands?|requests?|urges?|warns?|offers?|reads?)\b", I)
DEFENSIVE = re.compile(r"\b(never|don'?t|do not|stop|avoid|block|ignore|report|be wary|watch for|if (someone|anyone|a))\b", I)

STEPS = [
    (r"\bpress\s+(the\s+)?(windows|win|ctrl|control|alt|shift|enter|cmd|command|function|f\d{1,2})\b", "key presses for the viewer"),
    (r"\b(ctrl|control|alt|win(dows)?|cmd|command)\s*(\+|plus|and then)\s*\w+", "key combination"),
    (r"\b(type|run|paste|enter|execute|copy)\b[^.?!]{0,40}\b(command|powershell|terminal|run box|run dialog|script|code below)\b", "command for the viewer to run"),
    (r"\b(powershell|cmd\.exe|mshta|regedit|net user|curl\s+-|wget\s+http|base64 -d|invoke-\w+)\b", "command-line tool named"),
    (r"\bopen\s+(the\s+)?(run box|run dialog|terminal|command prompt|powershell)\b", "tells the viewer to open a command window"),
    (r"\b(step (one|two|three|1|2|3)|first,?\s+(open|press|type|run|go to))\b[^.?!]*\b(then|next)\b", "step-by-step walkthrough"),
]

MONEY = ["payment", "pay", "paid", "wire", "transfer", "gift card", "bank", "invoice", "money",
         "cash", "refund", "deposit", "account number", "crypto", "bitcoin", "funds", "urgent",
         "overdue", "fee", "wallet"]
MONEY_RE = [(w, re.compile(r"\b" + re.escape(w) + r"s?\b", I)) for w in MONEY]


def check(text: str):
    """-> list of {index, sentence, category, level, reason, match, suggestion}"""
    out = []
    for i, s in enumerate(sentences(text)):
        framed = bool(THIRD_PERSON.search(s))
        defensive = bool(DEFENSIVE.search(s))
        for pat, reason in ATTACKER:
            m = re.search(pat, s, I)
            if m:
                out.append({"index": i, "sentence": s, "category": "attacker_voice",
                            "level": "note" if (framed or defensive) else "warn",
                            "reason": reason, "match": m.group(0), "suggestion": SUGGEST_VOICE})
                break
        for pat, reason in STEPS:
            m = re.search(pat, s, I)
            if m:
                out.append({"index": i, "sentence": s, "category": "attack_steps", "level": "warn",
                            "reason": reason, "match": m.group(0), "suggestion": SUGGEST_STEPS})
                break
        hits = [w for w, rx in MONEY_RE if rx.search(s)]
        if "pay" in hits and "payment" in hits:
            hits.remove("pay")
        if len(hits) >= 3:
            out.append({"index": i, "sentence": s, "category": "money_words", "level": "warn",
                        "reason": f"{len(hits)} money words in one sentence", "match": ", ".join(hits),
                        "suggestion": SUGGEST_MONEY})
    return out
