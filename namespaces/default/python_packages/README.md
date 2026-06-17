# python_packages（registry・実レイヤ／同梱物はまだ無い）

`bundles` / `tools` などと**同列の 1 registry**（layer）。ここに Python の配布物
（wheel / sdist）を置き、juice の registry を **PyPI のように**使えるようにする。

**実レイヤ化済み（最小）:** `config.LAYERS` / `ENTRY_FILES` / `ALL_ORDER` に登録され、
`juice all list` / `juice python_package list` / `juice registry verify`（name=dir）/
`juice registry index` の横断対象になっている。

- 1 パッケージ = 1 ディレクトリ（`python_packages/<name>/`）。エントリは **`index.yml`**（純 YAML）で、
  最低限 `name`（= ディレクトリ名）を持つ。純 YAML なので OKF（`.md` concept document）検査の対象外。
- 配布物の中身（wheel / sdist の格納）・PEP 503 風の simple index 提供は**まだ未実装**（必要になってから＝YAGNI）。

現状この registry に同梱の python_package は無い（構造のみ。`list` は空）。同じ枠で `datasets` 等も同列に足せる。
用語と粒度は [docs/glossary.md](../../../docs/glossary.md)（「layer = registry」）を参照。
