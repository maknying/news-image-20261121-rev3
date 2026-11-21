# The World in One Page — 21 November 2026

A one-page newspaper drawn entirely by a program: 39 real stories from
Saturday 21 November 2026, grouped into 7 regions, with a lead story
(COP31 overtime in Antalya) beside a drawn globe and a band of numbers
at the foot.

## Run it

```sh
python3 main.py            # writes out/entry.png (or $MAKEFUN_OUTPUT_DIR)
```

`main.py` is standard library only and needs no network: it reads the
pre-rendered glyph atlas `atlas.bin` (built by `build_atlas.py` in the
work directory from DejaVu Sans) and writes a deterministic 1024x1024
PNG. Two runs produce identical bytes.

## Files

- `main.py` — the whole newspaper: atlas reader, pixel buffer, typesetter,
  PNG encoder, the 39 stories and the layout.
- `atlas.bin` — pre-rendered 1-bit glyph atlas (DejaVu Sans, 9 faces).
- `LICENSE` — MIT.

Sources for every story are documented in `SOURCES.md` in the work
directory (Reuters, AP, AFP, NYT, DW, CBC, UKMTO and others).
