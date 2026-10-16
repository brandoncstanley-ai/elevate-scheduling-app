import re

EXT_CODES = {"D7111", "D7140", "D7210", "D7220", "D7230", "D7250"}
FB_CODES = {"D7240", "D7241"}
GRAFT_CODES = {"D7953", "D6010", "D6104", "D7310", "D7311", "D7320", "D7321", "D4263", "D4264"}
PRF_CODES = {"D7921"}

ID_PATTERNS = [
    (r"\b(dob|d\.o\.b|date of birth|birth ?date)\b", "a birth date"),
    (r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", "a date"),
    (r"\b(mrn|chart\s*(#|no|number)|acct|account\s*#)", "a chart or account number"),
    (r"\b(patient|pt)\s*(name)?\s*:\s*[A-Za-z]", "a patient name"),
    (r"\bname\s*:", "a patient name"),
]
UNSURE = r"(not sure|unsure|maybe|possibl|\?|tbd|to be determined|ask dr|confirm with|pending)"
TOOTH_WORD = r"(#|\btooth\b|\bteeth\b|\bsite\b)"


def _teeth(clause):
    """Tooth numbers 1-32 or primary teeth A-T mentioned in one clause."""
    c = re.sub(r"\bD\d{4}\b", " ", clause, flags=re.I)        # drop CDT codes
    c = re.sub(r"\bx\s*\d+\b", " ", c, flags=re.I)             # drop 'x4' multipliers
    if not re.search(TOOTH_WORD, c, flags=re.I):
        return set()
    after = re.split(TOOTH_WORD, c, maxsplit=1, flags=re.I)[-1]
    nums = {int(n) for n in re.findall(r"\b([1-9]|[12]\d|3[0-2])\b", after)}
    letters = set(re.findall(r"#\s*([A-T])\b", c))
    return nums | letters


def _kind(clause):
    up = clause.upper()
    codes = set(re.findall(r"\bD\d{4}\b", up))
    low = clause.lower()
    kinds = set()
    if codes & FB_CODES or "full bony" in low or "full-bony" in low:
        kinds.add("fb")
    if codes & EXT_CODES or re.search(r"\b(ext|exts|extract\w*|remove|removal|simple|surgical ext)\b", low):
        kinds.add("ext")
    if codes & GRAFT_CODES or re.search(r"\b(graft\w*|implant\w*|alveoloplasty|alveo)\b", low):
        kinds.add("graft")
    if codes & PRF_CODES or re.search(r"\bprf\b|platelet[- ]rich", low):
        kinds.add("prf")
    return kinds


def read_plan(text):
    """Rule-based treatment-plan reader. Returns counts plus notes for anything unclear.
    No API, no network: everything happens in this function."""
    out = {"sedation": None, "teeth_removed": 0, "full_bony": 0, "graft": 0, "prf": 0,
           "notes": [], "refused": False}
    for pat, what in ID_PATTERNS:
        if re.search(pat, text, flags=re.I):
            out["refused"] = True
            out["notes"].append(f"Looks like it contains {what}. Remove patient identifiers and paste only the procedure lines.")
            return out
    low = text.lower()
    if re.search(r"\b(iv|sedation|sed|ivs|general anesthesia|ga)\b", low):
        out["sedation"] = True
    if re.search(r"\b(local only|local anesthesia only|local)\b", low) and not re.search(r"\b(iv|sedation|sed)\b", low):
        out["sedation"] = False

    # clauses: split on . ; newline, and on commas that start a new word-led phrase
    raw = re.split(r"[.;\n]+|,\s*(?=[A-Za-z]{3,})", text)
    clauses = []
    for c in raw:
        c = c.strip()
        if not c:
            continue
        k, t = _kind(c), _teeth(c)
        m = re.search(r"\bx\s*(\d+)\b", c, flags=re.I)
        mult = int(m.group(1)) if m else None
        unsure = bool(re.search(UNSURE, c, flags=re.I))
        if not k and t and clauses and clauses[-1]["kinds"] and not clauses[-1]["teeth"]:
            clauses[-1]["teeth"] = t             # "D7240 x4, teeth #1, 16, 17, 32"
            continue
        clauses.append({"text": c, "kinds": k, "teeth": t, "mult": mult, "unsure": unsure})

    ext_teeth, fb_teeth, anon_ext, anon_fb = set(), set(), 0, 0
    for c in clauses:
        if c["unsure"] and c["kinds"]:
            out["notes"].append(f"Unclear, not counted: '{c['text']}'. Confirm with Dr. Stanley.")
            continue
        if "fb" in c["kinds"] or "ext" in c["kinds"]:
            if c["teeth"]:
                ext_teeth |= c["teeth"]
                if "fb" in c["kinds"]:
                    fb_teeth |= c["teeth"]
            else:
                n = c["mult"] or 1
                anon_ext += n
                if "fb" in c["kinds"]:
                    anon_fb += n
                if not c["mult"]:
                    out["notes"].append(f"No tooth numbers in '{c['text']}'. Counted as 1 tooth.")
            if "fb" in c["kinds"] and "ext" in c["kinds"] and c["teeth"]:
                out["notes"].append(f"Mixed codes in one line: '{c['text']}'. Check the full-bony count.")
        if "graft" in c["kinds"]:
            out["graft"] = 1
        if "prf" in c["kinds"]:
            out["prf"] = 1
    out["teeth_removed"] = len(ext_teeth) + anon_ext
    out["full_bony"] = min(len(fb_teeth) + anon_fb, out["teeth_removed"])
    if out["sedation"] is None:
        out["notes"].append("Sedation or local is not stated. Assumed IV sedation.")
        out["sedation"] = True
    if out["teeth_removed"] == 0:
        out["notes"].append("No extractions found. This may not be a treatment plan. Set the counts by hand.")
    return out
