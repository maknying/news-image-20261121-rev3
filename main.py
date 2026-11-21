#!/usr/bin/env python3
"""The World in One Page — Saturday 21 November 2026.

A one-page newspaper drawn entirely by this program: standard library
only, no network, no clock, no randomness, so two runs write identical
bytes. It reads a pre-rendered glyph atlas (atlas.bin) sitting next to
it, paints the page into an RGB buffer and encodes that buffer as PNG.

The page: a masthead with the date, a lead story (COP31 overtime)
beside a drawn globe, then 38 more stories grouped into 7 regions over
two columns, and a band of numbers at the foot. 39 stories in all,
every one real and reported on 21 November 2026 (see SOURCES.md in the
work directory for the source of each story).
"""

import math
import os
import struct
import sys
import zlib

W = 1024
H = 1024

PAPER = (248, 243, 231)
INK = (24, 23, 20)
RED = (176, 36, 28)
BLUE = (28, 76, 138)
TEAL = (14, 110, 105)
FAINT = (170, 160, 142)
WHITE = (255, 255, 255)
SKY = (214, 230, 242)

B = 1
R = 0


# ------------------------------------------------------------------ atlas
def load_faces(path):
    """Read atlas.bin into {(bold, size): (ascent, descent, glyphs)}."""
    with open(path, "rb") as fh:
        blob = fh.read()
    if blob[:7] != b"ATLAS1\n":
        raise ValueError("atlas.bin has the wrong magic")
    at = 7
    (nfaces,) = struct.unpack_from(">I", blob, at)
    at += 4
    faces = {}
    for _ in range(nfaces):
        bold, size, asc, desc = struct.unpack_from(">HBHH", blob, at)
        at += 7
        (n,) = struct.unpack_from(">H", blob, at)
        at += 2
        glyphs = {}
        for _ in range(n):
            code, xo, yo, gw, gh, adv = struct.unpack_from(
                ">IhhHHH", blob, at)
            at += 14
            (nb,) = struct.unpack_from(">I", blob, at)
            at += 4
            glyphs[code] = (xo, yo, gw, gh, adv, blob[at:at + nb])
            at += nb
        faces[(bold, size)] = (asc, desc, glyphs)
    return faces


# ------------------------------------------------------------------ sheet
class Sheet:
    """An RGB pixel buffer with rectangle, line and circle primitives."""

    def __init__(self, width, height, bg):
        self.w = width
        self.h = height
        self.buf = bytearray(bytes(bg) * width * height)

    def dot(self, x, y, colour):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.buf[i:i + 3] = bytes(colour)

    def paint(self, x, y, w, h, colour):
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.w, x + w)
        y1 = min(self.h, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(colour) * (x1 - x0)
        for yy in range(y0, y1):
            i = (yy * self.w + x0) * 3
            self.buf[i:i + len(row)] = row

    def bar(self, x, y, w, colour, thick=1):
        self.paint(x, y, w, thick, colour)

    def box(self, x, y, w, h, colour, thick=1):
        self.paint(x, y, w, thick, colour)
        self.paint(x, y + h - thick, w, thick, colour)
        self.paint(x, y, thick, h, colour)
        self.paint(x + w - thick, y, thick, h, colour)

    def stroke(self, x0, y0, x1, y1, colour):
        """Bresenham line."""
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.dot(x0, y0, colour)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def disc(self, cx, cy, r, colour):
        for yy in range(cy - r, cy + r + 1):
            dy = yy - cy
            half = int(math.sqrt(max(0, r * r - dy * dy)))
            self.paint(cx - half, yy, half * 2 + 1, 1, colour)

    def ring(self, cx, cy, r, colour, thick=1):
        for t in range(thick):
            rr = r - t
            steps = max(64, int(2 * math.pi * rr))
            for i in range(steps):
                a = 2 * math.pi * i / steps
                self.dot(cx + int(rr * math.cos(a)),
                         cy + int(rr * math.sin(a)), colour)

    def oval(self, cx, cy, a, b, colour):
        steps = max(64, int(2 * math.pi * max(a, b)))
        for i in range(steps):
            ang = 2 * math.pi * i / steps
            self.dot(cx + int(a * math.cos(ang)),
                     cy + int(b * math.sin(ang)), colour)

    def slice(self, cx, cy, r, dy, colour):
        """Horizontal chord of a circle, dy below centre."""
        half = int(math.sqrt(max(0, r * r - dy * dy)))
        self.paint(cx - half, cy + dy, half * 2 + 1, 1, colour)


# ------------------------------------------------------------------- type
def glyph_for(faces, face, ch):
    _, _, table = faces[face]
    got = table.get(ord(ch))
    if got is None:
        got = table.get(ord("?"))
    return got


def text_width(faces, face, text, track=0):
    total = 0
    for ch in text:
        total += glyph_for(faces, face, ch)[4] + track
    return total - track if text else 0


def line_height(faces, face):
    asc, desc, _ = faces[face]
    return asc + desc


def draw_text(sheet, faces, face, x, y_top, text, colour, track=0):
    """Draw text; returns the pen x after the last glyph."""
    asc, _, _ = faces[face]
    base = y_top + asc
    pen = x
    for ch in text:
        xo, yo, gw, gh, adv, bits = glyph_for(faces, face, ch)
        if gw and gh:
            stride = (gw + 7) // 8
            for gy in range(gh):
                yy = base - asc + yo + gy
                if yy < 0 or yy >= sheet.h:
                    continue
                for bx in range(stride):
                    byte = bits[gy * stride + bx]
                    if not byte:
                        continue
                    for bit in range(8):
                        if byte & (0x80 >> bit):
                            xx = pen + xo + bx * 8 + bit
                            if 0 <= xx < sheet.w:
                                i = (yy * sheet.w + xx) * 3
                                sheet.buf[i:i + 3] = bytes(colour)
        pen += adv + track
    return pen


def draw_centred(sheet, faces, face, cx, y_top, text, colour, track=0):
    w = text_width(faces, face, text, track)
    draw_text(sheet, faces, face, cx - w // 2, y_top, text, colour, track)


def split_lines(faces, face, text, max_w, track=0):
    out = []
    for chunk in text.split("\n"):
        words = chunk.split(" ")
        cur = ""
        for word in words:
            trial = word if not cur else cur + " " + word
            if not cur or text_width(faces, face, trial, track) <= max_w:
                cur = trial
            else:
                out.append(cur)
                cur = word
        out.append(cur)
    return out


def draw_para(sheet, faces, face, x, y_top, text, max_w, colour,
              gap=3, track=0):
    step = line_height(faces, face) + gap
    y = y_top
    for ln in split_lines(faces, face, text, max_w, track):
        draw_text(sheet, faces, face, x, y, ln, colour, track)
        y += step
    return y


# -------------------------------------------------------------------- png
def png_bytes(sheet):
    raw = bytearray()
    stride = sheet.w * 3
    for yy in range(sheet.h):
        raw.append(0)
        raw += sheet.buf[yy * stride:(yy + 1) * stride]
    payload = zlib.compress(bytes(raw), 9)

    def chunk(kind, data):
        out = struct.pack(">I", len(data)) + kind + data
        return out + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    head = struct.pack(">IIBBBBB", sheet.w, sheet.h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head)
            + chunk(b"IDAT", payload) + chunk(b"IEND", b""))


# ---------------------------------------------------------------- content
TITLE = "THE WORLD IN ONE PAGE"
DATE = "SATURDAY, 21 NOVEMBER 2026"
TAG = "39 STORIES  \u00b7  7 REGIONS  \u00b7  ONE DAY"

LEAD_KICK = "ANTALYA \u2014 COP31 IN OVERTIME"
LEAD_HEAD = ["COP31 runs into overtime", "as fossil fuels vanish"]
LEAD_BODY = (
    "The summit missed its Friday deadline after the draft dropped fossil "
    "fuels and a $120bn fund. Talks run on."
)

# (region kicker, colour, [(dateline, one-line story), ...])
LEFT_COL = [
    ("MIDDLE EAST", RED, [
        ("RIYADH", "3 Houthi missiles downed; 2nd raid in days."),
        ("HODEIDAH", "Coalition hits port, Sanaa after raids."),
        ("HORMUZ", "Tanker attacks at monthly high; no hurt."),
        ("LEBANON", "Israeli strikes hit four southern districts."),
        ("BASRA", "Fire at power station kills four."),
    ]),
    ("EUROPE", BLUE, [
        ("COPENHAGEN", "Envoy to be expelled over murder plot."),
        ("BERLIN", "Defence chief sorry for \u2018stupid\u2019 remark."),
        ("PARIS", "Police sentenced over racist beating."),
        ("ISTANBUL", "Turkey takes control of Sozcu TV."),
        ("LONDON", "Leeds thrash Chelsea 4-1 at the Bridge."),
        ("TWICKENHAM", "England rout All Blacks 37-12, record win."),
    ]),
    ("UKRAINE WAR", TEAL, [
        ("KRYVYI RIH", "Missile kills 2, wounds 60 in hometown."),
        ("KYIV", "Bridges hit, power cut in mass strike."),
        ("CRIMEA", "Zelensky: the bridge \u2018won\u2019t remain\u2019."),
        ("UKRAINE", "148 drones in a night; 117 shot down."),
    ]),
    ("AMERICAS", RED, [
        ("SINALOA", "FBI most-wanted cartel boss captured."),
        ("SAN SALVADOR", "Bukele seeks an unusual third term."),
        ("BRAZIL", "Bacteria mosquitoes cut dengue cases 69%."),
        ("HAITI", "Salvadoran troops fight gangs in capital."),
    ]),
]

RIGHT_COL = [
    ("ASIA-PACIFIC", BLUE, [
        ("SHENZHEN", "Trump, Xi, Putin sign joint peace pact."),
        ("DHAKA", "50 Awami League homes burnt before return."),
        ("JAKARTA", "Daycare head jailed 5 years over abuse."),
        ("THE HAGUE", "ICJ: Myanmar guilty of genocide."),
        ("TOKYO", "Saudi-Japan agree oil stockpile deal."),
        ("JAPAN", "Pilotless air taxi carries a passenger."),
    ]),
    ("MARKETS & TECH", TEAL, [
        ("NEW YORK", "S&P falls 3.7% as AI sell-off spreads."),
        ("WALL ST", "Anthropic debuts as a $2 trillion firm."),
        ("CHIPS", "Nvidia halts H200 exports to China."),
        ("CALIFORNIA", "State probes Nvidia over ex-chief affair."),
        ("WASHINGTON", "FBI crime database reportedly hacked."),
        ("WHITE HOUSE", "Trump vows tax on data centres abroad."),
    ]),
    ("SCIENCE & WORLD", RED, [
        ("SPACE", "BepiColombo reaches Mercury orbit at last."),
        ("STRAIT", "Swimmer Pugh crosses Hormuz for wildlife."),
        ("GENEVA", "UN AI-weapons talks go on; no treaty yet."),
        ("ETHIOPIA", "700,000 displaced in the south."),
        ("VIRGINIA", "US loses measles elimination status."),
        ("CERN", "First evidence of ultra-rare decay found."),
        ("DEEP SPACE", "Voyager 1 now 24 light-hours away."),
    ]),
]

NUMBERS = [
    ("3", "missiles downed\nover Riyadh"),
    ("3.7%", "S&P 500 fall\nin a day"),
    ("700,000", "displaced in\nsouthern Ethiopia"),
    ("37-12", "record England win\nover the All Blacks"),
]

FOOT_A = ("Sources: Reuters \u00b7 AP \u00b7 AFP \u00b7 NYT \u00b7 DW \u00b7 CBC \u00b7 UKMTO"
          "  \u2014  Events of Saturday 21 November 2026")
FOOT_B = ("39 stories \u00b7 7 regions \u2014 Drawn by a program. No network, "
          "no AI images; every word set in type.")


# ------------------------------------------------------------------ layout
def draw_story(sheet, faces, x, y, width, place, text):
    """One story on a single line: bold dateline, regular rest."""
    head = place + " \u2014 "
    after = draw_text(sheet, faces, (B, 15), x, y, head, INK)
    draw_text(sheet, faces, (R, 15), after, y, text, INK)
    total = text_width(faces, (B, 15), head) + \
        text_width(faces, (R, 15), text)
    if total > width:
        raise ValueError("story too wide for column: %s %s (%d > %d)"
                         % (place, text, total, width))
    return y + 18


def draw_region(sheet, faces, x, width, y, regions):
    for kick, colour, items in regions:
        draw_text(sheet, faces, (B, 19), x, y, kick, colour, track=1)
        sheet.bar(x, y + 25, 52, colour, 3)
        y += 33
        for place, text in items:
            y = draw_story(sheet, faces, x, y, width, place, text)
        y += 6
    return y


def draw_globe(sheet, cx, cy, r):
    sheet.disc(cx, cy, r, BLUE)
    sheet.ring(cx, cy, r, INK, 2)
    sheet.ring(cx, cy, r + 7, INK, 1)
    sheet.oval(cx, cy, 24, r - 4, WHITE)
    sheet.oval(cx, cy, r - 4, 24, WHITE)
    sheet.slice(cx, cy, r - 2, -28, WHITE)
    sheet.slice(cx, cy, r - 2, 28, WHITE)
    sheet.disc(cx + 40, cy - 42, 5, RED)


def compose(faces):
    sheet = Sheet(W, H, PAPER)
    sheet.box(14, 14, W - 28, H - 28, INK, 2)
    sheet.box(20, 20, W - 40, H - 40, INK, 1)

    draw_centred(sheet, faces, (B, 64), W // 2, 32, TITLE, INK)
    draw_centred(sheet, faces, (B, 22), W // 2, 112, DATE, RED)
    draw_centred(sheet, faces, (R, 18), W // 2, 142, TAG, INK, track=3)
    sheet.bar(36, 172, W - 72, INK, 5)
    sheet.bar(36, 181, W - 72, INK, 1)

    # Lead story, left; drawn globe, right.
    draw_text(sheet, faces, (B, 19), 36, 192, LEAD_KICK, RED, track=1)
    y = 216
    for ln in LEAD_HEAD:
        draw_text(sheet, faces, (B, 30), 36, y, ln, INK)
        y += line_height(faces, (B, 30)) + 2
    y += 6
    y = draw_para(sheet, faces, (R, 20), 36, y, LEAD_BODY, 664,
                  INK, gap=3)
    draw_globe(sheet, 852, 272, 64)
    sheet.bar(36, 356, W - 72, FAINT, 1)

    # Region grid, two columns.
    left_end = draw_region(sheet, faces, 36, 469, 366, LEFT_COL)
    right_end = draw_region(sheet, faces, 519, 469, 366, RIGHT_COL)
    grid_end = max(left_end, right_end)
    sheet.paint(512, 368, 1, grid_end - 374, FAINT)

    # Numbers band.
    band_y = grid_end + 10
    band_h = 72
    sheet.box(36, band_y, W - 72, band_h, INK, 1)
    cell = (W - 72) // 4
    for i, (big, small) in enumerate(NUMBERS):
        cx = 36 + cell * i
        if i:
            sheet.paint(cx, band_y + 8, 1, band_h - 16, FAINT)
        draw_centred(sheet, faces, (B, 30), cx + cell // 2,
                     band_y + 4, big, RED)
        for j, ln in enumerate(small.split("\n")):
            draw_centred(sheet, faces, (R, 15), cx + cell // 2,
                         band_y + 38 + j * 17, ln, INK)

    sheet.bar(36, 956, W - 72, INK, 1)
    draw_centred(sheet, faces, (R, 14), W // 2, 964, FOOT_A, INK)
    draw_centred(sheet, faces, (R, 14), W // 2, 982, FOOT_B, INK)
    return sheet


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    faces = load_faces(os.path.join(here, "atlas.bin"))
    data = png_bytes(compose(faces))
    outdir = os.environ.get("MAKEFUN_OUTPUT_DIR")
    if not outdir:
        outdir = "/output" if os.path.isdir("/output") else "out"
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "entry.png")
    with open(path, "wb") as fh:
        fh.write(data)
    sys.stdout.write("wrote %s (%d bytes)\n" % (path, len(data)))


if __name__ == "__main__":
    main()
