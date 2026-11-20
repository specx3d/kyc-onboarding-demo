"""Generate fictional ID cards (TD1) and passports (TD3) with ground truth."""
import json
import random
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from kyc import mrz

ROOT = Path(__file__).parent
OUT = ROOT / "data" / "samples"
FONTS = Path("C:/Windows/Fonts")


def font(name, size):
    try:
        return ImageFont.truetype(str(FONTS / name), size)
    except OSError:
        return ImageFont.load_default()


# Fictional people only. "wl" = id of the related watchlist entry.
CASES = [
    dict(id="s01", kind="TD3", surname="BRANDT", given="ANNELIESE MARIE", number="C01X00T47", cc="DEU",
         dob=date(1985, 4, 12), sex="F", exp=date(2031, 6, 30), expected="none", status="pass"),
    dict(id="s02", kind="TD1", surname="NOWAK", given="TOMASZ JAN", number="ZK4417203", cc="POL",
         dob=date(1979, 9, 3), sex="M", exp=date(2032, 1, 14), expected="none", status="pass"),
    dict(id="s03", kind="TD3", surname="DUBOIS", given="CAMILLE", number="19AB35742", cc="FRA",
         dob=date(1992, 1, 28), sex="F", exp=date(2033, 3, 9), expected="none", status="pass"),
    dict(id="s04", kind="TD1", surname="FERN\u00c1NDEZ RUIZ", given="LUC\u00cdA", number="XDA229481", cc="ESP",
         dob=date(1990, 7, 19), sex="F", exp=date(2030, 11, 2), expected="none", status="pass"),
    dict(id="s05", kind="TD3", surname="DE VRIES", given="JORIS", number="NX5K9L2P7", cc="NLD",
         dob=date(1983, 12, 5), sex="M", exp=date(2029, 8, 21), expected="none", status="pass"),
    dict(id="s06", kind="TD1", surname="ROSSETTI", given="GIULIA", number="CA83120QZ", cc="ITA",
         dob=date(1996, 3, 30), sex="F", exp=date(2034, 5, 18), expected="none", status="pass"),
    dict(id="s07", kind="TD3", surname="HARGREAVES", given="OLIVER JAMES", number="533019284", cc="GBR",
         dob=date(1975, 10, 9), sex="M", exp=date(2031, 2, 27), expected="none", status="pass"),
    dict(id="s08", kind="TD3", surname="LEFEBVRE", given="ANTOINE", number="12CD90871", cc="FRA",
         dob=date(1970, 2, 14), sex="M", exp=date(2023, 5, 21), issues=["expired"], expected="none",
         status="reject"),
    dict(id="s09", kind="TD1", surname="ZIELINSKI", given="MAREK", number="ABC4821D7", cc="POL",
         dob=date(1982, 6, 11), sex="M", exp=date(2030, 4, 8), issues=["bad_check_digit"],
         tamper_number="ABC4821D1", expected="none", status="reject"),
    dict(id="s10", kind="TD3", surname="SCHMIDT", mrz_surname="SCHMITZ", given="KLARA", number="C22TR09KM",
         cc="DEU", dob=date(1988, 5, 25), sex="F", exp=date(2032, 9, 12), issues=["viz_mrz_mismatch"],
         expected="none", status="refer to analyst"),
    dict(id="s11", kind="TD1", surname="JANSSEN", given="PIETER", number="SPNB04917", cc="NLD",
         dob=date(1988, 8, 21), sex="M", exp=date(2031, 10, 3), degrade=True, expected="none", status="pass"),
    dict(id="s12", kind="TD3", surname="\u0141UKASZEWICZ", given="AGNIESZKA", number="EL7291044", cc="POL",
         dob=date(1991, 2, 17), sex="F", exp=date(2032, 7, 7), expected="none", status="pass"),
    dict(id="s13", kind="TD1", surname="DRAGOMIROVIC", given="MILOS", number="RS0048215", cc="SRB",
         dob=date(1971, 5, 23), sex="M", exp=date(2030, 12, 1), expected="true_match", wl="W-001",
         status="refer to analyst"),
    dict(id="s14", kind="TD3", surname="DRAGOMIROWICZ", given="MILOSZ", number="PL5583190", cc="POL",
         dob=date(1988, 11, 2), sex="M", exp=date(2033, 6, 15), expected="false_positive", wl="W-001",
         status="pass"),
]


def d_viz(d):
    return d.strftime("%d.%m.%Y")


def draw_person(dr, box):
    x0, y0, x1, y1 = box
    dr.rectangle(box, fill=(200, 200, 200), outline=(120, 120, 120), width=2)
    cx, w, h = (x0 + x1) // 2, x1 - x0, y1 - y0
    dr.ellipse((cx - w * .22, y0 + h * .14, cx + w * .22, y0 + h * .14 + w * .44), fill=(135, 135, 135))
    dr.pieslice((cx - w * .42, y0 + h * .62, cx + w * .42, y0 + h * 1.4), 180, 360, fill=(135, 135, 135))


def render(c, lines):
    td3 = c["kind"] == "TD3"
    W, H = (1100, 770) if td3 else (1000, 740)
    img = Image.new("RGB", (W, H), (236, 240, 232) if td3 else (230, 238, 246))
    dr = ImageDraw.Draw(img)
    f_h, f_l, f_v = font("arialbd.ttf", 34), font("arial.ttf", 17), font("arialbd.ttf", 29)
    f_m = font("consola.ttf", 38 if td3 else 34)
    dr.rectangle((0, 0, W, 70), fill=(60, 80, 110))
    dr.text((30, 16), "PASSPORT" if td3 else "IDENTITY CARD", font=f_h, fill="white")
    dr.text((W - 220, 22), f"SAMPLE  {c['cc']}", font=font("arialbd.ttf", 26), fill="white")
    draw_person(dr, (30, 95, 270, 395))
    dr.text((95, 400), "PHOTO", font=f_l, fill=(90, 90, 90))
    rows = [("Surname", c["surname"]), ("Given names", c["given"]),
            ("Document No.", c.get("tamper_number", c["number"])), ("Nationality", c["cc"]),
            ("Date of birth", d_viz(c["dob"])), ("Sex", c["sex"]),
            ("Date of expiry", d_viz(c["exp"])), ("Issuing country", c["cc"])]
    for i, (lab, val) in enumerate(rows):
        if i < 3:
            xx, yy = 310, 90 + i * 72
        else:
            xx, yy = 310 + ((i - 3) % 2) * 330, 90 + 3 * 72 + ((i - 3) // 2) * 72
        dr.text((xx, yy), lab.upper(), font=f_l, fill=(90, 90, 100))
        dr.text((xx, yy + 22), val, font=f_v, fill=(20, 20, 30))
    mh = len(lines) * 50 + 30
    dr.rectangle((0, H - mh, W, H), fill=(255, 255, 255))
    for i, l in enumerate(lines):
        dr.text((22, H - mh + 15 + i * 50), l, font=f_m, fill=(10, 10, 10))
    if c.get("degrade"):  # slight rotation + blur + noise
        img = img.rotate(3.4, resample=Image.BICUBIC, expand=True, fillcolor=(250, 250, 250))
        img = img.filter(ImageFilter.GaussianBlur(1.3))
        img = Image.blend(img, Image.effect_noise(img.size, 22).convert("RGB"), 0.16)
    return img


def build_mrz(c):
    d = dict(issuing=c["cc"], surname=c.get("mrz_surname", c["surname"]), given=c["given"],
             number=c["number"], nationality=c["cc"], dob=c["dob"], sex=c["sex"], expiry=c["exp"])
    td1 = c["kind"] == "TD1"
    lines = mrz.build_td1(**d) if td1 else mrz.build_td3(**d)
    if "tamper_number" in c:  # number altered, check digits left from the original
        li, i = (0, 5) if td1 else (1, 0)
        lines[li] = lines[li][:i] + mrz.pad(c["tamper_number"], 9) + lines[li][i + 9:]
    return lines


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    gt = {}
    for c in CASES:
        lines = build_mrz(c)
        fn = f"{c['id']}_{c['kind'].lower()}_{c['cc'].lower()}.png"
        render(c, lines).save(OUT / fn)
        gt[fn] = {
            "doc_type": c["kind"],
            "fields": {"surname": c["surname"], "given_names": c["given"],
                       "document_number": c.get("tamper_number", c["number"]),
                       "nationality": c["cc"], "date_of_birth": c["dob"].isoformat(), "sex": c["sex"],
                       "expiry_date": c["exp"].isoformat(), "issuing_country": c["cc"]},
            "mrz_lines": lines,
            "issues": c.get("issues", []),
            "screening": {"expected": c["expected"], "watchlist_id": c.get("wl")},
            "expected_status": c["status"],
        }
    (ROOT / "data" / "ground_truth.json").write_text(json.dumps(gt, indent=1, ensure_ascii=False),
                                                     encoding="utf-8")
    print(f"Generated {len(gt)} samples in {OUT}")


if __name__ == "__main__":
    main()
