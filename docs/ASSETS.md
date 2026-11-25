# FoodDiary 阶段 1 素材

## 食物贴纸

12 张透明贴纸由 Codex 内置 ImageGen 为 FoodDiary 单独生成，采用摄影风格。生成时使用文字描述作为输入。处理时裁去透明留白，保留 Alpha 通道，最长边缩至 520 px，并编码为 WebP。项目本地资产位于 [frontend/src/assets/food](../frontend/src/assets/food/)。

| 文件 | 生成提示中的食物主体 |
| --- | --- |
| `croissant.webp` | one golden butter croissant with distinctive flaky lamination, no plate |
| `milk.webp` | one squat clear glass of fresh milk with a simple rounded silhouette, no writing |
| `curry.webp` | a shallow ivory oval plate of Japanese beef curry, glossy caramel curry with potato and carrot, neatly mounded white rice |
| `ramen.webp` | a round dark ceramic bowl of shoyu ramen with egg, sliced pork, scallion and visible noodles |
| `sushi.webp` | a small set of three pieces of salmon nigiri sushi sitting together, no plate |
| `fried-rice.webp` | a round white plate with a mound of egg fried rice and scattered scallions |
| `tomato-eggs.webp` | a small ivory plate of homestyle Chinese tomato scrambled eggs, red tomato wedges and rich yellow egg |
| `cake.webp` | one triangular slice of Japanese strawberry shortcake with delicate sponge layers and a red strawberry on top, no plate |
| `coffee.webp` | a low ivory ceramic cup of coffee with realistic heart-shaped latte art and a small cream saucer |
| `strawberries.webp` | three fresh red strawberries with natural leaves arranged in one compact group |
| `burger.webp` | one thick artisan cheeseburger with toasted bun, crisp lettuce and beef, no wrapper or plate |
| `pasta.webp` | a shallow cream plate of red tomato spaghetti twirled into a natural mound with fresh basil |

每张图使用下列共同提示，其中 `{subject}` 替换为对应主体，并设置透明背景。

> Use case: photorealistic-natural. Asset: one FoodDiary food sticker for a Japanese-inspired editorial food journal. Subject: {subject}. One centered isolated subject, edge-to-edge with a little transparent breathing room. Photorealistic editorial food photography at a 40-degree overhead angle with soft daylight from upper left, true textures, neutral warm natural tones; subtle warm-white continuous die-cut sticker outline, make food the focus. Genuine transparent alpha everywhere outside the silhouette. No text, logos, additional decor, utensils, checkered pixels or cast shadow plane.

生成素材供 FoodDiary 原型使用，输出权利按适用的 OpenAI 服务条款处理。[OpenAI 使用条款](https://openai.com/policies/terms-of-use/)

## 字体、图形和截图

- 标题字使用 Google Fonts 提供的 Noto Serif SC 700 WOFF2 字形子集，按 SIL Open Font License 1.1 使用。正文采用设备上的中文无衬线字体。[字体来源](https://fonts.google.com/specimen/Noto+Serif+SC) · [许可证副本](../frontend/src/assets/fonts/OFL-NotoSerifSC.txt)
- 线性图标通过 `lucide-vue-next` 引用，按组件库许可证使用。纸纹、封面手绘路径和页面排版为项目原创实现。[Lucide 许可证](https://lucide.dev/license)
- 截图由本机 Chrome 在实际运行的应用中生成，来源为仓库内的演示样例数据。[截图索引](PHASE-1.md#六页面截图)
