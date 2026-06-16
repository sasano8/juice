# python_packages（registry・構造のみ／未実装）

`bundles` / `tools` などと**同列の 1 registry**（layer）を想定した将来枠。ここに Python の
パッケージ（wheel / sdist）を置き、juice の registry を **PyPI のように**使えるようにする構想。

現状は**構造だけ**で未実装:
- `config.LAYERS` には未登録（`all list` / `registry verify` の走査対象外＝inert）。
- 配置レイアウト・index 提供（PEP 503 風の simple index 等）は必要になってから（YAGNI）。

用語と粒度は [docs/glossary.md](../../../docs/glossary.md)（「layer = registry」）を参照。
同じ枠で `datasets` 等も同列に足せる。
