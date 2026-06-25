# ep7 プロンプト生成テスト（10場面）

> `prompt.build_for_cut` で組成。修正版 GLOBAL（A層）= 役割「美術監督の修正パス」／保持(構図・配置・カメラ)・修正(パース・構造・様式)・品位向上(手描き清書)の三分割。
> 全カット共通のため本書では [SCENE]/[CUT] 層のみ抜粋し、EN/JP全文は各カットの折りたたみに格納。
> データ源: scene_profiles + cut_board_map + cut_scene_info。


## CUT 15 — 花家_復活の儀の部屋c014～052

- board: `SZ#6_復活の儀の部屋(夜)_R1.png`
- resolved: scene_key=`復活の儀の部屋` / time=`夜` / weather=`—`

> [シーン] 舞台: 花家邸内の「復活の儀」の部屋（室内）（中国 南北朝〜初唐ごろ）。 在りうる構成物: 木組みの柱と梁、格子の木戸・衝立、一段高い祭壇／儀式の壇、垂れ幕・幡、板敷きまたは石敷きの床、据え置きの燭台・灯火台。 荘厳で簡素な時代劇の室内。建築・構造の線が画面を主導する。 避ける: 和風内装（畳・障子・襖）、西洋風・近代的な家具や調度、ファンタジー的／過剰な装飾。

> [カット] 夜の場面 — 暗さは陰影輪郭の密度と線の重ねだけで表す。白地に黒線のまま、グレーのベタやベタ黒の塊は使わない。

<details><summary>EN 全文（モデル入力）</summary>

```
You are a background art director's correction pass. Take a rough background layout (genzu) — a low-fidelity request sketch that may contain perspective errors and weak structure — and produce a corrected, near-delivery-quality BLACK-AND-WHITE background line drawing (haikei). This is a clean-up that FIXES and ELEVATES; it is neither a literal trace nor a free re-illustration.
PRESERVE (treat as directives): the composition, camera angle, eye-level and framing; the placement and front-to-back ordering of the major structures and natural elements; and the positions where characters stand, as spatial constraints. Do not zoom, crop, pan, re-center or re-stage what the layout shows.
CORRECT (fix what is wrong): resolve perspective so edges converge cleanly to the intended vanishing points; straighten weak or implausible structure and proportion; make architecture and props era- and culture-correct for the setting below. Keep the intended camera, but fix the geometry under it.
ELEVATE (raise the quality): render like a master background artist's careful hand-drawn pencil clean-up — line weight varied (heavier in the foreground, finer in the distance) with natural entry/exit tapering, texture suggested by light broken strokes. Modestly add structurally- and stylistically-correct detail so it reads as a finished drawing. Do NOT produce uniform vector outlines or a coloring-book look, and do not glamorize or upgrade any element beyond its role.
COLOR: monochrome output only — pure black ink lines on white, no grey shading or solid fills. Colored regions in the input are placeholder fills: read them as shapes and draw them as plain line work, never as color.
REMOVE: erase all production marks (handwritten notes, labels, numbers, frame borders, perspective guide lines, registration tap-holes). Also remove any character/person/animal and everything they hold, wear or carry, and rebuild the plain environment behind them. Keep furniture and fixtures that belong to the space (a bed, shelves, a lamp stay; a book in a hand goes).
DON'T over-correct: where a judgement is genuinely ambiguous, respect the layout's intent rather than inventing. MARGINS: the blank padding bands are intentional — leave them empty.

[SCENE] Setting: an interior ritual chamber in the Hua (花) family residence — Chinese Northern-and-Southern-Dynasties to early-Tang period. Elements likely present: timber post-and-beam framing with wooden pillars and crossbeams, latticed wooden screens and doors, a raised altar / ritual dais, hanging cloth drapery and banners, plank or stone flooring, standing candle/lamp stands. Solemn, sparse historical interior; architectural and structural lines should lead the drawing. Avoid: Japanese / wafu interior details (tatami, shoji, fusuma), European or modern furniture and fittings, fantasy or ornate decorative excess.

[CUT] Night scene — convey darkness only through denser, heavier shadow contours and selective line build-up; remain pure black line on white, no grey fill, no solid black masses.
```
</details>

<details><summary>JP 全文（確認用・モデルには渡さない）</summary>

```
あなたは背景美術監督の「修正パス」である。ラフな背景レイアウト（原図）— パースの狂いや弱い構造を含みうる、低精度の依頼用ラフ — を、納品手前の品質の白黒背景線画（背景）に仕上げる。
これは「直して品位を引き上げる」クリーンアップであり、字義通りのトレースでも、自由な描き直しでもない。
保持（指示として守る）: 構図・カメラアングル・アイレベル・画角／主要な建物と自然物の配置と前後関係／キャラの立ち位置（空間的な制約として）。原図が写しているものをズーム・トリミング・パン・再センタリング・再演出しない。
修正（狂いを直す）: エッジが意図した消失点へクリーンに収束するようパースを整える。弱い/不自然な構造と比率を正す。建築・調度を下記の時代・文化に正しく合わせる。意図したカメラは保ったまま、その下の幾何を直す。
品位向上: 一流の背景美術が丁寧に手描き鉛筆で清書したように描く — 線幅変調（近景は太く・遠景は繊細に）と自然な入り抜き、質感は軽い擦れ/破線で示唆。様式的・構造的に正しいディテールを控えめに足し、仕上がった絵として読めるようにする。
  均一なベクター輪郭や塗り絵調にしない。どの要素も役割以上に格上げ・豪華化しない。
色: 出力は白黒のみ。白地に黒のインク線、グレーの陰影やベタ塗りは禁止。入力中の色面はプレースホルダの塗りで、形として読み取り、色ではなく素の線画として描く。
除去: 制作用マーク（手書き指示・ラベル・番号・フレーム枠・パース補助線・タップ穴）を全て消す。
  さらに、キャラ/人物/動物と、その持ち物・着衣・携行物を全て消し、背後の素の環境を再構成する。
  その場所に属する家具・什器は残す（寝台・棚・燭台は残す／手に持つ本は消す）。
過修正の禁止: 判断が本当に曖昧な所は、捏造せず原図の意図を尊重する。余白: 周囲の空白パディング帯は意図的なもの。空白のまま残す。

[シーン] 舞台: 花家邸内の「復活の儀」の部屋（室内）（中国 南北朝〜初唐ごろ）。 在りうる構成物: 木組みの柱と梁、格子の木戸・衝立、一段高い祭壇／儀式の壇、垂れ幕・幡、板敷きまたは石敷きの床、据え置きの燭台・灯火台。 荘厳で簡素な時代劇の室内。建築・構造の線が画面を主導する。 避ける: 和風内装（畳・障子・襖）、西洋風・近代的な家具や調度、ファンタジー的／過剰な装飾。

[カット] 夜の場面 — 暗さは陰影輪郭の密度と線の重ねだけで表す。白地に黒線のまま、グレーのベタやベタ黒の塊は使わない。
```
</details>


## CUT 23 — 花家_復活の儀の部屋c014～052

- board: `SZ#6_復活の儀の部屋(夜)_R1.png`
- resolved: scene_key=`復活の儀の部屋` / time=`夜` / weather=`—`

> [シーン] 舞台: 花家邸内の「復活の儀」の部屋（室内）（中国 南北朝〜初唐ごろ）。 在りうる構成物: 木組みの柱と梁、格子の木戸・衝立、一段高い祭壇／儀式の壇、垂れ幕・幡、板敷きまたは石敷きの床、据え置きの燭台・灯火台。 荘厳で簡素な時代劇の室内。建築・構造の線が画面を主導する。 避ける: 和風内装（畳・障子・襖）、西洋風・近代的な家具や調度、ファンタジー的／過剰な装飾。

> [カット] 夜の場面 — 暗さは陰影輪郭の密度と線の重ねだけで表す。白地に黒線のまま、グレーのベタやベタ黒の塊は使わない。

<details><summary>EN 全文（モデル入力）</summary>

```
You are a background art director's correction pass. Take a rough background layout (genzu) — a low-fidelity request sketch that may contain perspective errors and weak structure — and produce a corrected, near-delivery-quality BLACK-AND-WHITE background line drawing (haikei). This is a clean-up that FIXES and ELEVATES; it is neither a literal trace nor a free re-illustration.
PRESERVE (treat as directives): the composition, camera angle, eye-level and framing; the placement and front-to-back ordering of the major structures and natural elements; and the positions where characters stand, as spatial constraints. Do not zoom, crop, pan, re-center or re-stage what the layout shows.
CORRECT (fix what is wrong): resolve perspective so edges converge cleanly to the intended vanishing points; straighten weak or implausible structure and proportion; make architecture and props era- and culture-correct for the setting below. Keep the intended camera, but fix the geometry under it.
ELEVATE (raise the quality): render like a master background artist's careful hand-drawn pencil clean-up — line weight varied (heavier in the foreground, finer in the distance) with natural entry/exit tapering, texture suggested by light broken strokes. Modestly add structurally- and stylistically-correct detail so it reads as a finished drawing. Do NOT produce uniform vector outlines or a coloring-book look, and do not glamorize or upgrade any element beyond its role.
COLOR: monochrome output only — pure black ink lines on white, no grey shading or solid fills. Colored regions in the input are placeholder fills: read them as shapes and draw them as plain line work, never as color.
REMOVE: erase all production marks (handwritten notes, labels, numbers, frame borders, perspective guide lines, registration tap-holes). Also remove any character/person/animal and everything they hold, wear or carry, and rebuild the plain environment behind them. Keep furniture and fixtures that belong to the space (a bed, shelves, a lamp stay; a book in a hand goes).
DON'T over-correct: where a judgement is genuinely ambiguous, respect the layout's intent rather than inventing. MARGINS: the blank padding bands are intentional — leave them empty.

[SCENE] Setting: an interior ritual chamber in the Hua (花) family residence — Chinese Northern-and-Southern-Dynasties to early-Tang period. Elements likely present: timber post-and-beam framing with wooden pillars and crossbeams, latticed wooden screens and doors, a raised altar / ritual dais, hanging cloth drapery and banners, plank or stone flooring, standing candle/lamp stands. Solemn, sparse historical interior; architectural and structural lines should lead the drawing. Avoid: Japanese / wafu interior details (tatami, shoji, fusuma), European or modern furniture and fittings, fantasy or ornate decorative excess.

[CUT] Night scene — convey darkness only through denser, heavier shadow contours and selective line build-up; remain pure black line on white, no grey fill, no solid black masses.
```
</details>

<details><summary>JP 全文（確認用・モデルには渡さない）</summary>

```
あなたは背景美術監督の「修正パス」である。ラフな背景レイアウト（原図）— パースの狂いや弱い構造を含みうる、低精度の依頼用ラフ — を、納品手前の品質の白黒背景線画（背景）に仕上げる。
これは「直して品位を引き上げる」クリーンアップであり、字義通りのトレースでも、自由な描き直しでもない。
保持（指示として守る）: 構図・カメラアングル・アイレベル・画角／主要な建物と自然物の配置と前後関係／キャラの立ち位置（空間的な制約として）。原図が写しているものをズーム・トリミング・パン・再センタリング・再演出しない。
修正（狂いを直す）: エッジが意図した消失点へクリーンに収束するようパースを整える。弱い/不自然な構造と比率を正す。建築・調度を下記の時代・文化に正しく合わせる。意図したカメラは保ったまま、その下の幾何を直す。
品位向上: 一流の背景美術が丁寧に手描き鉛筆で清書したように描く — 線幅変調（近景は太く・遠景は繊細に）と自然な入り抜き、質感は軽い擦れ/破線で示唆。様式的・構造的に正しいディテールを控えめに足し、仕上がった絵として読めるようにする。
  均一なベクター輪郭や塗り絵調にしない。どの要素も役割以上に格上げ・豪華化しない。
色: 出力は白黒のみ。白地に黒のインク線、グレーの陰影やベタ塗りは禁止。入力中の色面はプレースホルダの塗りで、形として読み取り、色ではなく素の線画として描く。
除去: 制作用マーク（手書き指示・ラベル・番号・フレーム枠・パース補助線・タップ穴）を全て消す。
  さらに、キャラ/人物/動物と、その持ち物・着衣・携行物を全て消し、背後の素の環境を再構成する。
  その場所に属する家具・什器は残す（寝台・棚・燭台は残す／手に持つ本は消す）。
過修正の禁止: 判断が本当に曖昧な所は、捏造せず原図の意図を尊重する。余白: 周囲の空白パディング帯は意図的なもの。空白のまま残す。

[シーン] 舞台: 花家邸内の「復活の儀」の部屋（室内）（中国 南北朝〜初唐ごろ）。 在りうる構成物: 木組みの柱と梁、格子の木戸・衝立、一段高い祭壇／儀式の壇、垂れ幕・幡、板敷きまたは石敷きの床、据え置きの燭台・灯火台。 荘厳で簡素な時代劇の室内。建築・構造の線が画面を主導する。 避ける: 和風内装（畳・障子・襖）、西洋風・近代的な家具や調度、ファンタジー的／過剰な装飾。

[カット] 夜の場面 — 暗さは陰影輪郭の密度と線の重ねだけで表す。白地に黒線のまま、グレーのベタやベタ黒の塊は使わない。
```
</details>


## CUT 47 — 花家_復活の儀の部屋c014～052

- board: `#6_花氏邸_全景（夜）_R2.png`
- resolved: scene_key=`花氏邸_全景` / time=`夜` / weather=`—`

> [シーン] 舞台: 花氏邸の全景（外観・引き）（中国 南北朝〜初唐ごろ）。 在りうる構成物: 瓦屋根（反り軒）の塀で囲まれた邸、木組みの門と建屋、中庭の塀・段状の軒、石段・敷石のアプローチ、周囲の樹木・庭の植栽。 引きの確立ショット。屋根のライン・塀・邸全体のシルエットが構図を支える。 避ける: 日本の城郭・寺社のシルエット、西洋建築、近代的な建物・インフラ。

> [カット] 夜の場面 — 暗さは陰影輪郭の密度と線の重ねだけで表す。白地に黒線のまま、グレーのベタやベタ黒の塊は使わない。

<details><summary>EN 全文（モデル入力）</summary>

```
You are a background art director's correction pass. Take a rough background layout (genzu) — a low-fidelity request sketch that may contain perspective errors and weak structure — and produce a corrected, near-delivery-quality BLACK-AND-WHITE background line drawing (haikei). This is a clean-up that FIXES and ELEVATES; it is neither a literal trace nor a free re-illustration.
PRESERVE (treat as directives): the composition, camera angle, eye-level and framing; the placement and front-to-back ordering of the major structures and natural elements; and the positions where characters stand, as spatial constraints. Do not zoom, crop, pan, re-center or re-stage what the layout shows.
CORRECT (fix what is wrong): resolve perspective so edges converge cleanly to the intended vanishing points; straighten weak or implausible structure and proportion; make architecture and props era- and culture-correct for the setting below. Keep the intended camera, but fix the geometry under it.
ELEVATE (raise the quality): render like a master background artist's careful hand-drawn pencil clean-up — line weight varied (heavier in the foreground, finer in the distance) with natural entry/exit tapering, texture suggested by light broken strokes. Modestly add structurally- and stylistically-correct detail so it reads as a finished drawing. Do NOT produce uniform vector outlines or a coloring-book look, and do not glamorize or upgrade any element beyond its role.
COLOR: monochrome output only — pure black ink lines on white, no grey shading or solid fills. Colored regions in the input are placeholder fills: read them as shapes and draw them as plain line work, never as color.
REMOVE: erase all production marks (handwritten notes, labels, numbers, frame borders, perspective guide lines, registration tap-holes). Also remove any character/person/animal and everything they hold, wear or carry, and rebuild the plain environment behind them. Keep furniture and fixtures that belong to the space (a bed, shelves, a lamp stay; a book in a hand goes).
DON'T over-correct: where a judgement is genuinely ambiguous, respect the layout's intent rather than inventing. MARGINS: the blank padding bands are intentional — leave them empty.

[SCENE] Setting: an exterior establishing view of the Hua (花) family estate — Chinese Northern-and-Southern-Dynasties to early-Tang period. Elements likely present: a walled compound with tiled, upturned-eave roofs, timber-framed gates and halls, courtyard walls and stepped eaves, stone steps and paved approach, surrounding trees and garden planting. Wide establishing exterior; rooflines, walls and the overall compound silhouette carry the composition. Avoid: Japanese castle or temple silhouettes, European architecture, modern buildings or infrastructure.

[CUT] Night scene — convey darkness only through denser, heavier shadow contours and selective line build-up; remain pure black line on white, no grey fill, no solid black masses.
```
</details>

<details><summary>JP 全文（確認用・モデルには渡さない）</summary>

```
あなたは背景美術監督の「修正パス」である。ラフな背景レイアウト（原図）— パースの狂いや弱い構造を含みうる、低精度の依頼用ラフ — を、納品手前の品質の白黒背景線画（背景）に仕上げる。
これは「直して品位を引き上げる」クリーンアップであり、字義通りのトレースでも、自由な描き直しでもない。
保持（指示として守る）: 構図・カメラアングル・アイレベル・画角／主要な建物と自然物の配置と前後関係／キャラの立ち位置（空間的な制約として）。原図が写しているものをズーム・トリミング・パン・再センタリング・再演出しない。
修正（狂いを直す）: エッジが意図した消失点へクリーンに収束するようパースを整える。弱い/不自然な構造と比率を正す。建築・調度を下記の時代・文化に正しく合わせる。意図したカメラは保ったまま、その下の幾何を直す。
品位向上: 一流の背景美術が丁寧に手描き鉛筆で清書したように描く — 線幅変調（近景は太く・遠景は繊細に）と自然な入り抜き、質感は軽い擦れ/破線で示唆。様式的・構造的に正しいディテールを控えめに足し、仕上がった絵として読めるようにする。
  均一なベクター輪郭や塗り絵調にしない。どの要素も役割以上に格上げ・豪華化しない。
色: 出力は白黒のみ。白地に黒のインク線、グレーの陰影やベタ塗りは禁止。入力中の色面はプレースホルダの塗りで、形として読み取り、色ではなく素の線画として描く。
除去: 制作用マーク（手書き指示・ラベル・番号・フレーム枠・パース補助線・タップ穴）を全て消す。
  さらに、キャラ/人物/動物と、その持ち物・着衣・携行物を全て消し、背後の素の環境を再構成する。
  その場所に属する家具・什器は残す（寝台・棚・燭台は残す／手に持つ本は消す）。
過修正の禁止: 判断が本当に曖昧な所は、捏造せず原図の意図を尊重する。余白: 周囲の空白パディング帯は意図的なもの。空白のまま残す。

[シーン] 舞台: 花氏邸の全景（外観・引き）（中国 南北朝〜初唐ごろ）。 在りうる構成物: 瓦屋根（反り軒）の塀で囲まれた邸、木組みの門と建屋、中庭の塀・段状の軒、石段・敷石のアプローチ、周囲の樹木・庭の植栽。 引きの確立ショット。屋根のライン・塀・邸全体のシルエットが構図を支える。 避ける: 日本の城郭・寺社のシルエット、西洋建築、近代的な建物・インフラ。

[カット] 夜の場面 — 暗さは陰影輪郭の密度と線の重ねだけで表す。白地に黒線のまま、グレーのベタやベタ黒の塊は使わない。
```
</details>


## CUT 53 — 森_夜c053～206

- board: `#6#7森の中（夜）R.png`
- resolved: scene_key=`森` / time=`夜` / weather=`—`

> [シーン] 舞台: 山岳地帯の自然林（森の中）（中国 南北朝〜初唐ごろを思わせる山岳地帯）。 在りうる構成物: 細く背の高い落葉広葉樹（楡・槐・楓・雑木）の幹が林立、中〜低木・下草・苔むした地面、手前から奥へ抜ける踏み分けの土道（雨時は濡れた泥）、奥の樹々は重なって霞み、奥行きを示す。 自然主義的で素朴。樹木は主役化させず、空間の骨格と奥行きを補強する程度に。特定の構成物を豪華に見せない。 避ける: 熱帯植物・ヤシ・密林ジャングル、日本庭園風の植栽、巨大ファンタジー樹。

> [カット] 夜の場面 — 暗さは陰影輪郭の密度と線の重ねだけで表す。白地に黒線のまま、グレーのベタやベタ黒の塊は使わない。

<details><summary>EN 全文（モデル入力）</summary>

```
You are a background art director's correction pass. Take a rough background layout (genzu) — a low-fidelity request sketch that may contain perspective errors and weak structure — and produce a corrected, near-delivery-quality BLACK-AND-WHITE background line drawing (haikei). This is a clean-up that FIXES and ELEVATES; it is neither a literal trace nor a free re-illustration.
PRESERVE (treat as directives): the composition, camera angle, eye-level and framing; the placement and front-to-back ordering of the major structures and natural elements; and the positions where characters stand, as spatial constraints. Do not zoom, crop, pan, re-center or re-stage what the layout shows.
CORRECT (fix what is wrong): resolve perspective so edges converge cleanly to the intended vanishing points; straighten weak or implausible structure and proportion; make architecture and props era- and culture-correct for the setting below. Keep the intended camera, but fix the geometry under it.
ELEVATE (raise the quality): render like a master background artist's careful hand-drawn pencil clean-up — line weight varied (heavier in the foreground, finer in the distance) with natural entry/exit tapering, texture suggested by light broken strokes. Modestly add structurally- and stylistically-correct detail so it reads as a finished drawing. Do NOT produce uniform vector outlines or a coloring-book look, and do not glamorize or upgrade any element beyond its role.
COLOR: monochrome output only — pure black ink lines on white, no grey shading or solid fills. Colored regions in the input are placeholder fills: read them as shapes and draw them as plain line work, never as color.
REMOVE: erase all production marks (handwritten notes, labels, numbers, frame borders, perspective guide lines, registration tap-holes). Also remove any character/person/animal and everything they hold, wear or carry, and rebuild the plain environment behind them. Keep furniture and fixtures that belong to the space (a bed, shelves, a lamp stay; a book in a hand goes).
DON'T over-correct: where a judgement is genuinely ambiguous, respect the layout's intent rather than inventing. MARGINS: the blank padding bands are intentional — leave them empty.

[SCENE] Setting: a natural temperate forest in a mountainous region — Chinese Northern-and-Southern-Dynasties to early-Tang period, mountainous wilderness. Elements likely present: tall, slender trunks of temperate deciduous broadleaf trees (elm, pagoda tree, maple, mixed scrub) standing in stands, mid- and low shrubs, undergrowth and a moss-covered ground, a trodden earth/mud path receding from foreground into depth, distant trees overlapping and fading to suggest spatial depth. Naturalistic and plain; trees are not the subject — they reinforce the spatial skeleton and depth, not a single ornate feature. Avoid: tropical plants, palms, dense jungle, Japanese-garden-style planting, giant fantasy trees.

[CUT] Night scene — convey darkness only through denser, heavier shadow contours and selective line build-up; remain pure black line on white, no grey fill, no solid black masses.
```
</details>

<details><summary>JP 全文（確認用・モデルには渡さない）</summary>

```
あなたは背景美術監督の「修正パス」である。ラフな背景レイアウト（原図）— パースの狂いや弱い構造を含みうる、低精度の依頼用ラフ — を、納品手前の品質の白黒背景線画（背景）に仕上げる。
これは「直して品位を引き上げる」クリーンアップであり、字義通りのトレースでも、自由な描き直しでもない。
保持（指示として守る）: 構図・カメラアングル・アイレベル・画角／主要な建物と自然物の配置と前後関係／キャラの立ち位置（空間的な制約として）。原図が写しているものをズーム・トリミング・パン・再センタリング・再演出しない。
修正（狂いを直す）: エッジが意図した消失点へクリーンに収束するようパースを整える。弱い/不自然な構造と比率を正す。建築・調度を下記の時代・文化に正しく合わせる。意図したカメラは保ったまま、その下の幾何を直す。
品位向上: 一流の背景美術が丁寧に手描き鉛筆で清書したように描く — 線幅変調（近景は太く・遠景は繊細に）と自然な入り抜き、質感は軽い擦れ/破線で示唆。様式的・構造的に正しいディテールを控えめに足し、仕上がった絵として読めるようにする。
  均一なベクター輪郭や塗り絵調にしない。どの要素も役割以上に格上げ・豪華化しない。
色: 出力は白黒のみ。白地に黒のインク線、グレーの陰影やベタ塗りは禁止。入力中の色面はプレースホルダの塗りで、形として読み取り、色ではなく素の線画として描く。
除去: 制作用マーク（手書き指示・ラベル・番号・フレーム枠・パース補助線・タップ穴）を全て消す。
  さらに、キャラ/人物/動物と、その持ち物・着衣・携行物を全て消し、背後の素の環境を再構成する。
  その場所に属する家具・什器は残す（寝台・棚・燭台は残す／手に持つ本は消す）。
過修正の禁止: 判断が本当に曖昧な所は、捏造せず原図の意図を尊重する。余白: 周囲の空白パディング帯は意図的なもの。空白のまま残す。

[シーン] 舞台: 山岳地帯の自然林（森の中）（中国 南北朝〜初唐ごろを思わせる山岳地帯）。 在りうる構成物: 細く背の高い落葉広葉樹（楡・槐・楓・雑木）の幹が林立、中〜低木・下草・苔むした地面、手前から奥へ抜ける踏み分けの土道（雨時は濡れた泥）、奥の樹々は重なって霞み、奥行きを示す。 自然主義的で素朴。樹木は主役化させず、空間の骨格と奥行きを補強する程度に。特定の構成物を豪華に見せない。 避ける: 熱帯植物・ヤシ・密林ジャングル、日本庭園風の植栽、巨大ファンタジー樹。

[カット] 夜の場面 — 暗さは陰影輪郭の密度と線の重ねだけで表す。白地に黒線のまま、グレーのベタやベタ黒の塊は使わない。
```
</details>


## CUT 207 — 森_朝c207～239

- board: `森明けげ方.png`
- resolved: scene_key=`森` / time=`—` / weather=`—`

> [シーン] 舞台: 山岳地帯の自然林（森の中）（中国 南北朝〜初唐ごろを思わせる山岳地帯）。 在りうる構成物: 細く背の高い落葉広葉樹（楡・槐・楓・雑木）の幹が林立、中〜低木・下草・苔むした地面、手前から奥へ抜ける踏み分けの土道（雨時は濡れた泥）、奥の樹々は重なって霞み、奥行きを示す。 自然主義的で素朴。樹木は主役化させず、空間の骨格と奥行きを補強する程度に。特定の構成物を豪華に見せない。 避ける: 熱帯植物・ヤシ・密林ジャングル、日本庭園風の植栽、巨大ファンタジー樹。

<details><summary>EN 全文（モデル入力）</summary>

```
You are a background art director's correction pass. Take a rough background layout (genzu) — a low-fidelity request sketch that may contain perspective errors and weak structure — and produce a corrected, near-delivery-quality BLACK-AND-WHITE background line drawing (haikei). This is a clean-up that FIXES and ELEVATES; it is neither a literal trace nor a free re-illustration.
PRESERVE (treat as directives): the composition, camera angle, eye-level and framing; the placement and front-to-back ordering of the major structures and natural elements; and the positions where characters stand, as spatial constraints. Do not zoom, crop, pan, re-center or re-stage what the layout shows.
CORRECT (fix what is wrong): resolve perspective so edges converge cleanly to the intended vanishing points; straighten weak or implausible structure and proportion; make architecture and props era- and culture-correct for the setting below. Keep the intended camera, but fix the geometry under it.
ELEVATE (raise the quality): render like a master background artist's careful hand-drawn pencil clean-up — line weight varied (heavier in the foreground, finer in the distance) with natural entry/exit tapering, texture suggested by light broken strokes. Modestly add structurally- and stylistically-correct detail so it reads as a finished drawing. Do NOT produce uniform vector outlines or a coloring-book look, and do not glamorize or upgrade any element beyond its role.
COLOR: monochrome output only — pure black ink lines on white, no grey shading or solid fills. Colored regions in the input are placeholder fills: read them as shapes and draw them as plain line work, never as color.
REMOVE: erase all production marks (handwritten notes, labels, numbers, frame borders, perspective guide lines, registration tap-holes). Also remove any character/person/animal and everything they hold, wear or carry, and rebuild the plain environment behind them. Keep furniture and fixtures that belong to the space (a bed, shelves, a lamp stay; a book in a hand goes).
DON'T over-correct: where a judgement is genuinely ambiguous, respect the layout's intent rather than inventing. MARGINS: the blank padding bands are intentional — leave them empty.

[SCENE] Setting: a natural temperate forest in a mountainous region — Chinese Northern-and-Southern-Dynasties to early-Tang period, mountainous wilderness. Elements likely present: tall, slender trunks of temperate deciduous broadleaf trees (elm, pagoda tree, maple, mixed scrub) standing in stands, mid- and low shrubs, undergrowth and a moss-covered ground, a trodden earth/mud path receding from foreground into depth, distant trees overlapping and fading to suggest spatial depth. Naturalistic and plain; trees are not the subject — they reinforce the spatial skeleton and depth, not a single ornate feature. Avoid: tropical plants, palms, dense jungle, Japanese-garden-style planting, giant fantasy trees.
```
</details>

<details><summary>JP 全文（確認用・モデルには渡さない）</summary>

```
あなたは背景美術監督の「修正パス」である。ラフな背景レイアウト（原図）— パースの狂いや弱い構造を含みうる、低精度の依頼用ラフ — を、納品手前の品質の白黒背景線画（背景）に仕上げる。
これは「直して品位を引き上げる」クリーンアップであり、字義通りのトレースでも、自由な描き直しでもない。
保持（指示として守る）: 構図・カメラアングル・アイレベル・画角／主要な建物と自然物の配置と前後関係／キャラの立ち位置（空間的な制約として）。原図が写しているものをズーム・トリミング・パン・再センタリング・再演出しない。
修正（狂いを直す）: エッジが意図した消失点へクリーンに収束するようパースを整える。弱い/不自然な構造と比率を正す。建築・調度を下記の時代・文化に正しく合わせる。意図したカメラは保ったまま、その下の幾何を直す。
品位向上: 一流の背景美術が丁寧に手描き鉛筆で清書したように描く — 線幅変調（近景は太く・遠景は繊細に）と自然な入り抜き、質感は軽い擦れ/破線で示唆。様式的・構造的に正しいディテールを控えめに足し、仕上がった絵として読めるようにする。
  均一なベクター輪郭や塗り絵調にしない。どの要素も役割以上に格上げ・豪華化しない。
色: 出力は白黒のみ。白地に黒のインク線、グレーの陰影やベタ塗りは禁止。入力中の色面はプレースホルダの塗りで、形として読み取り、色ではなく素の線画として描く。
除去: 制作用マーク（手書き指示・ラベル・番号・フレーム枠・パース補助線・タップ穴）を全て消す。
  さらに、キャラ/人物/動物と、その持ち物・着衣・携行物を全て消し、背後の素の環境を再構成する。
  その場所に属する家具・什器は残す（寝台・棚・燭台は残す／手に持つ本は消す）。
過修正の禁止: 判断が本当に曖昧な所は、捏造せず原図の意図を尊重する。余白: 周囲の空白パディング帯は意図的なもの。空白のまま残す。

[シーン] 舞台: 山岳地帯の自然林（森の中）（中国 南北朝〜初唐ごろを思わせる山岳地帯）。 在りうる構成物: 細く背の高い落葉広葉樹（楡・槐・楓・雑木）の幹が林立、中〜低木・下草・苔むした地面、手前から奥へ抜ける踏み分けの土道（雨時は濡れた泥）、奥の樹々は重なって霞み、奥行きを示す。 自然主義的で素朴。樹木は主役化させず、空間の骨格と奥行きを補強する程度に。特定の構成物を豪華に見せない。 避ける: 熱帯植物・ヤシ・密林ジャングル、日本庭園風の植栽、巨大ファンタジー樹。
```
</details>


## CUT 240 — 森_よどんだ朝c247～256

- board: `#6 寺院内　道然たちの寝室（昼）_R2.png`
- resolved: scene_key=`道観_寝室` / time=`昼` / weather=`—`

> [シーン] 舞台: 山中の道観内の僧坊・寝室（室内）（中国 南北朝〜初唐ごろ／道観の室内）。 在りうる構成物: 木組みの簡素な室内（あらわしの柱・梁）、低い寝台（牀）と薄い寝具、木の格子窓・板戸から差す昼光、質素な調度（卓・棚・灯火）。 静かで質素な昼の室内。柔らかい昼光。落ち着いた休息のトーン。 避ける: 和室の要素（畳・障子・襖・布団）、西洋・近代の家具、華美・宮殿的な装飾。

> [カット] 昼 — ニュートラルで均一な光。陰影の輪郭線は控えめ。

<details><summary>EN 全文（モデル入力）</summary>

```
You are a background art director's correction pass. Take a rough background layout (genzu) — a low-fidelity request sketch that may contain perspective errors and weak structure — and produce a corrected, near-delivery-quality BLACK-AND-WHITE background line drawing (haikei). This is a clean-up that FIXES and ELEVATES; it is neither a literal trace nor a free re-illustration.
PRESERVE (treat as directives): the composition, camera angle, eye-level and framing; the placement and front-to-back ordering of the major structures and natural elements; and the positions where characters stand, as spatial constraints. Do not zoom, crop, pan, re-center or re-stage what the layout shows.
CORRECT (fix what is wrong): resolve perspective so edges converge cleanly to the intended vanishing points; straighten weak or implausible structure and proportion; make architecture and props era- and culture-correct for the setting below. Keep the intended camera, but fix the geometry under it.
ELEVATE (raise the quality): render like a master background artist's careful hand-drawn pencil clean-up — line weight varied (heavier in the foreground, finer in the distance) with natural entry/exit tapering, texture suggested by light broken strokes. Modestly add structurally- and stylistically-correct detail so it reads as a finished drawing. Do NOT produce uniform vector outlines or a coloring-book look, and do not glamorize or upgrade any element beyond its role.
COLOR: monochrome output only — pure black ink lines on white, no grey shading or solid fills. Colored regions in the input are placeholder fills: read them as shapes and draw them as plain line work, never as color.
REMOVE: erase all production marks (handwritten notes, labels, numbers, frame borders, perspective guide lines, registration tap-holes). Also remove any character/person/animal and everything they hold, wear or carry, and rebuild the plain environment behind them. Keep furniture and fixtures that belong to the space (a bed, shelves, a lamp stay; a book in a hand goes).
DON'T over-correct: where a judgement is genuinely ambiguous, respect the layout's intent rather than inventing. MARGINS: the blank padding bands are intentional — leave them empty.

[SCENE] Setting: a monks' sleeping quarters inside a mountain Daoist temple — Chinese Northern-and-Southern-Dynasties to early-Tang period, temple interior. Elements likely present: simple timber-framed interior with exposed posts and beams, a low wooden bed (couch) with thin bedding, wooden lattice window and plank door letting in daylight, sparse plain furnishings (low table, shelf, lamp). Quiet, humble daytime interior; gentle daylight. Calm, restful tone. Avoid: Japanese washitsu details (tatami, shoji, fusuma, futon), European or modern furniture, ornate or palatial decoration.

[CUT] Daytime — neutral even lighting; restrained shadow contour lines.
```
</details>

<details><summary>JP 全文（確認用・モデルには渡さない）</summary>

```
あなたは背景美術監督の「修正パス」である。ラフな背景レイアウト（原図）— パースの狂いや弱い構造を含みうる、低精度の依頼用ラフ — を、納品手前の品質の白黒背景線画（背景）に仕上げる。
これは「直して品位を引き上げる」クリーンアップであり、字義通りのトレースでも、自由な描き直しでもない。
保持（指示として守る）: 構図・カメラアングル・アイレベル・画角／主要な建物と自然物の配置と前後関係／キャラの立ち位置（空間的な制約として）。原図が写しているものをズーム・トリミング・パン・再センタリング・再演出しない。
修正（狂いを直す）: エッジが意図した消失点へクリーンに収束するようパースを整える。弱い/不自然な構造と比率を正す。建築・調度を下記の時代・文化に正しく合わせる。意図したカメラは保ったまま、その下の幾何を直す。
品位向上: 一流の背景美術が丁寧に手描き鉛筆で清書したように描く — 線幅変調（近景は太く・遠景は繊細に）と自然な入り抜き、質感は軽い擦れ/破線で示唆。様式的・構造的に正しいディテールを控えめに足し、仕上がった絵として読めるようにする。
  均一なベクター輪郭や塗り絵調にしない。どの要素も役割以上に格上げ・豪華化しない。
色: 出力は白黒のみ。白地に黒のインク線、グレーの陰影やベタ塗りは禁止。入力中の色面はプレースホルダの塗りで、形として読み取り、色ではなく素の線画として描く。
除去: 制作用マーク（手書き指示・ラベル・番号・フレーム枠・パース補助線・タップ穴）を全て消す。
  さらに、キャラ/人物/動物と、その持ち物・着衣・携行物を全て消し、背後の素の環境を再構成する。
  その場所に属する家具・什器は残す（寝台・棚・燭台は残す／手に持つ本は消す）。
過修正の禁止: 判断が本当に曖昧な所は、捏造せず原図の意図を尊重する。余白: 周囲の空白パディング帯は意図的なもの。空白のまま残す。

[シーン] 舞台: 山中の道観内の僧坊・寝室（室内）（中国 南北朝〜初唐ごろ／道観の室内）。 在りうる構成物: 木組みの簡素な室内（あらわしの柱・梁）、低い寝台（牀）と薄い寝具、木の格子窓・板戸から差す昼光、質素な調度（卓・棚・灯火）。 静かで質素な昼の室内。柔らかい昼光。落ち着いた休息のトーン。 避ける: 和室の要素（畳・障子・襖・布団）、西洋・近代の家具、華美・宮殿的な装飾。

[カット] 昼 — ニュートラルで均一な光。陰影の輪郭線は控えめ。
```
</details>


## CUT 257 — 道観_寝室c257～273

- board: `#6_山の中道教の寺院（昼）_R1.png`
- resolved: scene_key=`道観_寝室` / time=`昼` / weather=`—`

> [シーン] 舞台: 山中の道観内の僧坊・寝室（室内）（中国 南北朝〜初唐ごろ／道観の室内）。 在りうる構成物: 木組みの簡素な室内（あらわしの柱・梁）、低い寝台（牀）と薄い寝具、木の格子窓・板戸から差す昼光、質素な調度（卓・棚・灯火）。 静かで質素な昼の室内。柔らかい昼光。落ち着いた休息のトーン。 避ける: 和室の要素（畳・障子・襖・布団）、西洋・近代の家具、華美・宮殿的な装飾。

> [カット] 昼 — ニュートラルで均一な光。陰影の輪郭線は控えめ。

<details><summary>EN 全文（モデル入力）</summary>

```
You are a background art director's correction pass. Take a rough background layout (genzu) — a low-fidelity request sketch that may contain perspective errors and weak structure — and produce a corrected, near-delivery-quality BLACK-AND-WHITE background line drawing (haikei). This is a clean-up that FIXES and ELEVATES; it is neither a literal trace nor a free re-illustration.
PRESERVE (treat as directives): the composition, camera angle, eye-level and framing; the placement and front-to-back ordering of the major structures and natural elements; and the positions where characters stand, as spatial constraints. Do not zoom, crop, pan, re-center or re-stage what the layout shows.
CORRECT (fix what is wrong): resolve perspective so edges converge cleanly to the intended vanishing points; straighten weak or implausible structure and proportion; make architecture and props era- and culture-correct for the setting below. Keep the intended camera, but fix the geometry under it.
ELEVATE (raise the quality): render like a master background artist's careful hand-drawn pencil clean-up — line weight varied (heavier in the foreground, finer in the distance) with natural entry/exit tapering, texture suggested by light broken strokes. Modestly add structurally- and stylistically-correct detail so it reads as a finished drawing. Do NOT produce uniform vector outlines or a coloring-book look, and do not glamorize or upgrade any element beyond its role.
COLOR: monochrome output only — pure black ink lines on white, no grey shading or solid fills. Colored regions in the input are placeholder fills: read them as shapes and draw them as plain line work, never as color.
REMOVE: erase all production marks (handwritten notes, labels, numbers, frame borders, perspective guide lines, registration tap-holes). Also remove any character/person/animal and everything they hold, wear or carry, and rebuild the plain environment behind them. Keep furniture and fixtures that belong to the space (a bed, shelves, a lamp stay; a book in a hand goes).
DON'T over-correct: where a judgement is genuinely ambiguous, respect the layout's intent rather than inventing. MARGINS: the blank padding bands are intentional — leave them empty.

[SCENE] Setting: a monks' sleeping quarters inside a mountain Daoist temple — Chinese Northern-and-Southern-Dynasties to early-Tang period, temple interior. Elements likely present: simple timber-framed interior with exposed posts and beams, a low wooden bed (couch) with thin bedding, wooden lattice window and plank door letting in daylight, sparse plain furnishings (low table, shelf, lamp). Quiet, humble daytime interior; gentle daylight. Calm, restful tone. Avoid: Japanese washitsu details (tatami, shoji, fusuma, futon), European or modern furniture, ornate or palatial decoration.

[CUT] Daytime — neutral even lighting; restrained shadow contour lines.
```
</details>

<details><summary>JP 全文（確認用・モデルには渡さない）</summary>

```
あなたは背景美術監督の「修正パス」である。ラフな背景レイアウト（原図）— パースの狂いや弱い構造を含みうる、低精度の依頼用ラフ — を、納品手前の品質の白黒背景線画（背景）に仕上げる。
これは「直して品位を引き上げる」クリーンアップであり、字義通りのトレースでも、自由な描き直しでもない。
保持（指示として守る）: 構図・カメラアングル・アイレベル・画角／主要な建物と自然物の配置と前後関係／キャラの立ち位置（空間的な制約として）。原図が写しているものをズーム・トリミング・パン・再センタリング・再演出しない。
修正（狂いを直す）: エッジが意図した消失点へクリーンに収束するようパースを整える。弱い/不自然な構造と比率を正す。建築・調度を下記の時代・文化に正しく合わせる。意図したカメラは保ったまま、その下の幾何を直す。
品位向上: 一流の背景美術が丁寧に手描き鉛筆で清書したように描く — 線幅変調（近景は太く・遠景は繊細に）と自然な入り抜き、質感は軽い擦れ/破線で示唆。様式的・構造的に正しいディテールを控えめに足し、仕上がった絵として読めるようにする。
  均一なベクター輪郭や塗り絵調にしない。どの要素も役割以上に格上げ・豪華化しない。
色: 出力は白黒のみ。白地に黒のインク線、グレーの陰影やベタ塗りは禁止。入力中の色面はプレースホルダの塗りで、形として読み取り、色ではなく素の線画として描く。
除去: 制作用マーク（手書き指示・ラベル・番号・フレーム枠・パース補助線・タップ穴）を全て消す。
  さらに、キャラ/人物/動物と、その持ち物・着衣・携行物を全て消し、背後の素の環境を再構成する。
  その場所に属する家具・什器は残す（寝台・棚・燭台は残す／手に持つ本は消す）。
過修正の禁止: 判断が本当に曖昧な所は、捏造せず原図の意図を尊重する。余白: 周囲の空白パディング帯は意図的なもの。空白のまま残す。

[シーン] 舞台: 山中の道観内の僧坊・寝室（室内）（中国 南北朝〜初唐ごろ／道観の室内）。 在りうる構成物: 木組みの簡素な室内（あらわしの柱・梁）、低い寝台（牀）と薄い寝具、木の格子窓・板戸から差す昼光、質素な調度（卓・棚・灯火）。 静かで質素な昼の室内。柔らかい昼光。落ち着いた休息のトーン。 避ける: 和室の要素（畳・障子・襖・布団）、西洋・近代の家具、華美・宮殿的な装飾。

[カット] 昼 — ニュートラルで均一な光。陰影の輪郭線は控えめ。
```
</details>


## CUT 274 — 道観c274～289

- board: `寺院内 台所 食堂(夕方_雨)_R2_.png`
- resolved: scene_key=`道観` / time=`夕方` / weather=`雨`

> [シーン] 舞台: 山中の道教寺院（道観）の境内・建屋（中国 南北朝〜初唐ごろ／山岳の道教寺院）。 在りうる構成物: 瓦または茅葺の堂宇、木組みの柱と梁、木の回廊・縁・欄干、石段・土間の中庭・敷石のアプローチ、簡素な調度。背景は山の自然林。 質素な中国山岳の道観。屋根のライン・木組み・山の地形が画面を支える。光は柔らかく、一部小雨。 避ける: 日本の寺社シルエット（鳥居・五重塔・唐破風）、西洋建築、豪壮で過剰な宮殿装飾／近代要素。

> [カット] 夕方 — 長い方向性のある落ち影の輪郭。線のみ、グレー無し。 雨 — 濡れた地面や反射は線だけで示唆する。原図に無い限りグレーのベタや雨脚は足さない。

<details><summary>EN 全文（モデル入力）</summary>

```
You are a background art director's correction pass. Take a rough background layout (genzu) — a low-fidelity request sketch that may contain perspective errors and weak structure — and produce a corrected, near-delivery-quality BLACK-AND-WHITE background line drawing (haikei). This is a clean-up that FIXES and ELEVATES; it is neither a literal trace nor a free re-illustration.
PRESERVE (treat as directives): the composition, camera angle, eye-level and framing; the placement and front-to-back ordering of the major structures and natural elements; and the positions where characters stand, as spatial constraints. Do not zoom, crop, pan, re-center or re-stage what the layout shows.
CORRECT (fix what is wrong): resolve perspective so edges converge cleanly to the intended vanishing points; straighten weak or implausible structure and proportion; make architecture and props era- and culture-correct for the setting below. Keep the intended camera, but fix the geometry under it.
ELEVATE (raise the quality): render like a master background artist's careful hand-drawn pencil clean-up — line weight varied (heavier in the foreground, finer in the distance) with natural entry/exit tapering, texture suggested by light broken strokes. Modestly add structurally- and stylistically-correct detail so it reads as a finished drawing. Do NOT produce uniform vector outlines or a coloring-book look, and do not glamorize or upgrade any element beyond its role.
COLOR: monochrome output only — pure black ink lines on white, no grey shading or solid fills. Colored regions in the input are placeholder fills: read them as shapes and draw them as plain line work, never as color.
REMOVE: erase all production marks (handwritten notes, labels, numbers, frame borders, perspective guide lines, registration tap-holes). Also remove any character/person/animal and everything they hold, wear or carry, and rebuild the plain environment behind them. Keep furniture and fixtures that belong to the space (a bed, shelves, a lamp stay; a book in a hand goes).
DON'T over-correct: where a judgement is genuinely ambiguous, respect the layout's intent rather than inventing. MARGINS: the blank padding bands are intentional — leave them empty.

[SCENE] Setting: a Daoist temple compound in the mountains — Chinese Northern-and-Southern-Dynasties to early-Tang period, mountain Daoist temple. Elements likely present: tiled or thatched temple halls with timber post-and-beam framing, wooden colonnades / verandas and railings, stone steps, packed-earth courtyard and paved approach, plain ritual fittings; set into a mountain forest backdrop. Humble Chinese mountain Daoist temple; rooflines, timber framing and the mountain setting carry the shot. Soft light; some scenes have light rain. Avoid: Japanese temple/shrine silhouettes (torii, pagoda, karahafu), European architecture, grand ornate palace decoration; modern elements.

[CUT] Evening — longer directional cast-shadow contours; line only, no grey. Rain — suggest wet ground and reflections with line only; do not add grey fills or rain streaks unless they are present in the layout.
```
</details>

<details><summary>JP 全文（確認用・モデルには渡さない）</summary>

```
あなたは背景美術監督の「修正パス」である。ラフな背景レイアウト（原図）— パースの狂いや弱い構造を含みうる、低精度の依頼用ラフ — を、納品手前の品質の白黒背景線画（背景）に仕上げる。
これは「直して品位を引き上げる」クリーンアップであり、字義通りのトレースでも、自由な描き直しでもない。
保持（指示として守る）: 構図・カメラアングル・アイレベル・画角／主要な建物と自然物の配置と前後関係／キャラの立ち位置（空間的な制約として）。原図が写しているものをズーム・トリミング・パン・再センタリング・再演出しない。
修正（狂いを直す）: エッジが意図した消失点へクリーンに収束するようパースを整える。弱い/不自然な構造と比率を正す。建築・調度を下記の時代・文化に正しく合わせる。意図したカメラは保ったまま、その下の幾何を直す。
品位向上: 一流の背景美術が丁寧に手描き鉛筆で清書したように描く — 線幅変調（近景は太く・遠景は繊細に）と自然な入り抜き、質感は軽い擦れ/破線で示唆。様式的・構造的に正しいディテールを控えめに足し、仕上がった絵として読めるようにする。
  均一なベクター輪郭や塗り絵調にしない。どの要素も役割以上に格上げ・豪華化しない。
色: 出力は白黒のみ。白地に黒のインク線、グレーの陰影やベタ塗りは禁止。入力中の色面はプレースホルダの塗りで、形として読み取り、色ではなく素の線画として描く。
除去: 制作用マーク（手書き指示・ラベル・番号・フレーム枠・パース補助線・タップ穴）を全て消す。
  さらに、キャラ/人物/動物と、その持ち物・着衣・携行物を全て消し、背後の素の環境を再構成する。
  その場所に属する家具・什器は残す（寝台・棚・燭台は残す／手に持つ本は消す）。
過修正の禁止: 判断が本当に曖昧な所は、捏造せず原図の意図を尊重する。余白: 周囲の空白パディング帯は意図的なもの。空白のまま残す。

[シーン] 舞台: 山中の道教寺院（道観）の境内・建屋（中国 南北朝〜初唐ごろ／山岳の道教寺院）。 在りうる構成物: 瓦または茅葺の堂宇、木組みの柱と梁、木の回廊・縁・欄干、石段・土間の中庭・敷石のアプローチ、簡素な調度。背景は山の自然林。 質素な中国山岳の道観。屋根のライン・木組み・山の地形が画面を支える。光は柔らかく、一部小雨。 避ける: 日本の寺社シルエット（鳥居・五重塔・唐破風）、西洋建築、豪壮で過剰な宮殿装飾／近代要素。

[カット] 夕方 — 長い方向性のある落ち影の輪郭。線のみ、グレー無し。 雨 — 濡れた地面や反射は線だけで示唆する。原図に無い限りグレーのベタや雨脚は足さない。
```
</details>


## CUT 293 — 道観c274～289

- board: `#6_山の中道教の寺院_R1_朝.png`
- resolved: scene_key=`道観` / time=`朝` / weather=`—`

> [シーン] 舞台: 山中の道教寺院（道観）の境内・建屋（中国 南北朝〜初唐ごろ／山岳の道教寺院）。 在りうる構成物: 瓦または茅葺の堂宇、木組みの柱と梁、木の回廊・縁・欄干、石段・土間の中庭・敷石のアプローチ、簡素な調度。背景は山の自然林。 質素な中国山岳の道観。屋根のライン・木組み・山の地形が画面を支える。光は柔らかく、一部小雨。 避ける: 日本の寺社シルエット（鳥居・五重塔・唐破風）、西洋建築、豪壮で過剰な宮殿装飾／近代要素。

> [カット] 朝 — 均一で穏やかな光。落ち影は最小限、すっきりした軽い線。

<details><summary>EN 全文（モデル入力）</summary>

```
You are a background art director's correction pass. Take a rough background layout (genzu) — a low-fidelity request sketch that may contain perspective errors and weak structure — and produce a corrected, near-delivery-quality BLACK-AND-WHITE background line drawing (haikei). This is a clean-up that FIXES and ELEVATES; it is neither a literal trace nor a free re-illustration.
PRESERVE (treat as directives): the composition, camera angle, eye-level and framing; the placement and front-to-back ordering of the major structures and natural elements; and the positions where characters stand, as spatial constraints. Do not zoom, crop, pan, re-center or re-stage what the layout shows.
CORRECT (fix what is wrong): resolve perspective so edges converge cleanly to the intended vanishing points; straighten weak or implausible structure and proportion; make architecture and props era- and culture-correct for the setting below. Keep the intended camera, but fix the geometry under it.
ELEVATE (raise the quality): render like a master background artist's careful hand-drawn pencil clean-up — line weight varied (heavier in the foreground, finer in the distance) with natural entry/exit tapering, texture suggested by light broken strokes. Modestly add structurally- and stylistically-correct detail so it reads as a finished drawing. Do NOT produce uniform vector outlines or a coloring-book look, and do not glamorize or upgrade any element beyond its role.
COLOR: monochrome output only — pure black ink lines on white, no grey shading or solid fills. Colored regions in the input are placeholder fills: read them as shapes and draw them as plain line work, never as color.
REMOVE: erase all production marks (handwritten notes, labels, numbers, frame borders, perspective guide lines, registration tap-holes). Also remove any character/person/animal and everything they hold, wear or carry, and rebuild the plain environment behind them. Keep furniture and fixtures that belong to the space (a bed, shelves, a lamp stay; a book in a hand goes).
DON'T over-correct: where a judgement is genuinely ambiguous, respect the layout's intent rather than inventing. MARGINS: the blank padding bands are intentional — leave them empty.

[SCENE] Setting: a Daoist temple compound in the mountains — Chinese Northern-and-Southern-Dynasties to early-Tang period, mountain Daoist temple. Elements likely present: tiled or thatched temple halls with timber post-and-beam framing, wooden colonnades / verandas and railings, stone steps, packed-earth courtyard and paved approach, plain ritual fittings; set into a mountain forest backdrop. Humble Chinese mountain Daoist temple; rooflines, timber framing and the mountain setting carry the shot. Soft light; some scenes have light rain. Avoid: Japanese temple/shrine silhouettes (torii, pagoda, karahafu), European architecture, grand ornate palace decoration; modern elements.

[CUT] Morning — even gentle light; minimal cast shadow, clean light linework.
```
</details>

<details><summary>JP 全文（確認用・モデルには渡さない）</summary>

```
あなたは背景美術監督の「修正パス」である。ラフな背景レイアウト（原図）— パースの狂いや弱い構造を含みうる、低精度の依頼用ラフ — を、納品手前の品質の白黒背景線画（背景）に仕上げる。
これは「直して品位を引き上げる」クリーンアップであり、字義通りのトレースでも、自由な描き直しでもない。
保持（指示として守る）: 構図・カメラアングル・アイレベル・画角／主要な建物と自然物の配置と前後関係／キャラの立ち位置（空間的な制約として）。原図が写しているものをズーム・トリミング・パン・再センタリング・再演出しない。
修正（狂いを直す）: エッジが意図した消失点へクリーンに収束するようパースを整える。弱い/不自然な構造と比率を正す。建築・調度を下記の時代・文化に正しく合わせる。意図したカメラは保ったまま、その下の幾何を直す。
品位向上: 一流の背景美術が丁寧に手描き鉛筆で清書したように描く — 線幅変調（近景は太く・遠景は繊細に）と自然な入り抜き、質感は軽い擦れ/破線で示唆。様式的・構造的に正しいディテールを控えめに足し、仕上がった絵として読めるようにする。
  均一なベクター輪郭や塗り絵調にしない。どの要素も役割以上に格上げ・豪華化しない。
色: 出力は白黒のみ。白地に黒のインク線、グレーの陰影やベタ塗りは禁止。入力中の色面はプレースホルダの塗りで、形として読み取り、色ではなく素の線画として描く。
除去: 制作用マーク（手書き指示・ラベル・番号・フレーム枠・パース補助線・タップ穴）を全て消す。
  さらに、キャラ/人物/動物と、その持ち物・着衣・携行物を全て消し、背後の素の環境を再構成する。
  その場所に属する家具・什器は残す（寝台・棚・燭台は残す／手に持つ本は消す）。
過修正の禁止: 判断が本当に曖昧な所は、捏造せず原図の意図を尊重する。余白: 周囲の空白パディング帯は意図的なもの。空白のまま残す。

[シーン] 舞台: 山中の道教寺院（道観）の境内・建屋（中国 南北朝〜初唐ごろ／山岳の道教寺院）。 在りうる構成物: 瓦または茅葺の堂宇、木組みの柱と梁、木の回廊・縁・欄干、石段・土間の中庭・敷石のアプローチ、簡素な調度。背景は山の自然林。 質素な中国山岳の道観。屋根のライン・木組み・山の地形が画面を支える。光は柔らかく、一部小雨。 避ける: 日本の寺社シルエット（鳥居・五重塔・唐破風）、西洋建築、豪壮で過剰な宮殿装飾／近代要素。

[カット] 朝 — 均一で穏やかな光。落ち影は最小限、すっきりした軽い線。
```
</details>


## CUT 294 — 森c293～

- board: `#6#7森の中（昼）.png`
- resolved: scene_key=`森` / time=`昼` / weather=`—`

> [シーン] 舞台: 山岳地帯の自然林（森の中）（中国 南北朝〜初唐ごろを思わせる山岳地帯）。 在りうる構成物: 細く背の高い落葉広葉樹（楡・槐・楓・雑木）の幹が林立、中〜低木・下草・苔むした地面、手前から奥へ抜ける踏み分けの土道（雨時は濡れた泥）、奥の樹々は重なって霞み、奥行きを示す。 自然主義的で素朴。樹木は主役化させず、空間の骨格と奥行きを補強する程度に。特定の構成物を豪華に見せない。 避ける: 熱帯植物・ヤシ・密林ジャングル、日本庭園風の植栽、巨大ファンタジー樹。

> [カット] 昼 — ニュートラルで均一な光。陰影の輪郭線は控えめ。

<details><summary>EN 全文（モデル入力）</summary>

```
You are a background art director's correction pass. Take a rough background layout (genzu) — a low-fidelity request sketch that may contain perspective errors and weak structure — and produce a corrected, near-delivery-quality BLACK-AND-WHITE background line drawing (haikei). This is a clean-up that FIXES and ELEVATES; it is neither a literal trace nor a free re-illustration.
PRESERVE (treat as directives): the composition, camera angle, eye-level and framing; the placement and front-to-back ordering of the major structures and natural elements; and the positions where characters stand, as spatial constraints. Do not zoom, crop, pan, re-center or re-stage what the layout shows.
CORRECT (fix what is wrong): resolve perspective so edges converge cleanly to the intended vanishing points; straighten weak or implausible structure and proportion; make architecture and props era- and culture-correct for the setting below. Keep the intended camera, but fix the geometry under it.
ELEVATE (raise the quality): render like a master background artist's careful hand-drawn pencil clean-up — line weight varied (heavier in the foreground, finer in the distance) with natural entry/exit tapering, texture suggested by light broken strokes. Modestly add structurally- and stylistically-correct detail so it reads as a finished drawing. Do NOT produce uniform vector outlines or a coloring-book look, and do not glamorize or upgrade any element beyond its role.
COLOR: monochrome output only — pure black ink lines on white, no grey shading or solid fills. Colored regions in the input are placeholder fills: read them as shapes and draw them as plain line work, never as color.
REMOVE: erase all production marks (handwritten notes, labels, numbers, frame borders, perspective guide lines, registration tap-holes). Also remove any character/person/animal and everything they hold, wear or carry, and rebuild the plain environment behind them. Keep furniture and fixtures that belong to the space (a bed, shelves, a lamp stay; a book in a hand goes).
DON'T over-correct: where a judgement is genuinely ambiguous, respect the layout's intent rather than inventing. MARGINS: the blank padding bands are intentional — leave them empty.

[SCENE] Setting: a natural temperate forest in a mountainous region — Chinese Northern-and-Southern-Dynasties to early-Tang period, mountainous wilderness. Elements likely present: tall, slender trunks of temperate deciduous broadleaf trees (elm, pagoda tree, maple, mixed scrub) standing in stands, mid- and low shrubs, undergrowth and a moss-covered ground, a trodden earth/mud path receding from foreground into depth, distant trees overlapping and fading to suggest spatial depth. Naturalistic and plain; trees are not the subject — they reinforce the spatial skeleton and depth, not a single ornate feature. Avoid: tropical plants, palms, dense jungle, Japanese-garden-style planting, giant fantasy trees.

[CUT] Daytime — neutral even lighting; restrained shadow contour lines.
```
</details>

<details><summary>JP 全文（確認用・モデルには渡さない）</summary>

```
あなたは背景美術監督の「修正パス」である。ラフな背景レイアウト（原図）— パースの狂いや弱い構造を含みうる、低精度の依頼用ラフ — を、納品手前の品質の白黒背景線画（背景）に仕上げる。
これは「直して品位を引き上げる」クリーンアップであり、字義通りのトレースでも、自由な描き直しでもない。
保持（指示として守る）: 構図・カメラアングル・アイレベル・画角／主要な建物と自然物の配置と前後関係／キャラの立ち位置（空間的な制約として）。原図が写しているものをズーム・トリミング・パン・再センタリング・再演出しない。
修正（狂いを直す）: エッジが意図した消失点へクリーンに収束するようパースを整える。弱い/不自然な構造と比率を正す。建築・調度を下記の時代・文化に正しく合わせる。意図したカメラは保ったまま、その下の幾何を直す。
品位向上: 一流の背景美術が丁寧に手描き鉛筆で清書したように描く — 線幅変調（近景は太く・遠景は繊細に）と自然な入り抜き、質感は軽い擦れ/破線で示唆。様式的・構造的に正しいディテールを控えめに足し、仕上がった絵として読めるようにする。
  均一なベクター輪郭や塗り絵調にしない。どの要素も役割以上に格上げ・豪華化しない。
色: 出力は白黒のみ。白地に黒のインク線、グレーの陰影やベタ塗りは禁止。入力中の色面はプレースホルダの塗りで、形として読み取り、色ではなく素の線画として描く。
除去: 制作用マーク（手書き指示・ラベル・番号・フレーム枠・パース補助線・タップ穴）を全て消す。
  さらに、キャラ/人物/動物と、その持ち物・着衣・携行物を全て消し、背後の素の環境を再構成する。
  その場所に属する家具・什器は残す（寝台・棚・燭台は残す／手に持つ本は消す）。
過修正の禁止: 判断が本当に曖昧な所は、捏造せず原図の意図を尊重する。余白: 周囲の空白パディング帯は意図的なもの。空白のまま残す。

[シーン] 舞台: 山岳地帯の自然林（森の中）（中国 南北朝〜初唐ごろを思わせる山岳地帯）。 在りうる構成物: 細く背の高い落葉広葉樹（楡・槐・楓・雑木）の幹が林立、中〜低木・下草・苔むした地面、手前から奥へ抜ける踏み分けの土道（雨時は濡れた泥）、奥の樹々は重なって霞み、奥行きを示す。 自然主義的で素朴。樹木は主役化させず、空間の骨格と奥行きを補強する程度に。特定の構成物を豪華に見せない。 避ける: 熱帯植物・ヤシ・密林ジャングル、日本庭園風の植栽、巨大ファンタジー樹。

[カット] 昼 — ニュートラルで均一な光。陰影の輪郭線は控えめ。
```
</details>
