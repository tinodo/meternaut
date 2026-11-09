"""The one stylesheet of every page: the file docs/ui/meternaut-ui.css of the style guide (docs/ui/style-guide.html), carried here as a string because the pages read no file.

A test (tests/test_web_style.py) pins that the string and the file are the same, so a change to the style is made in both. Fluent 2 design tokens as CSS custom properties (light, dark
and forced colors), no script and no outside file.
"""

STYLE = r"""/* Meternaut UI, version 1 (2026-11-09): the one stylesheet of every page. Fluent 2 design tokens as CSS custom properties (light, dark, forced colors), no script, no outside file.
   docs/ui/style-guide.html shows each part and the rules. The pages of the app carry this file as the string in cases/web/style.py (the web package reads no file), and a test pins that the two are the same. */
:root{color-scheme:light dark;
--fontFamilyBase:"Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif;--fontFamilyMonospace:"Cascadia Mono",Consolas,"Courier New",monospace;
--fontSizeBase200:.75rem;--fontSizeBase300:.875rem;--fontSizeBase400:1rem;--fontSizeBase500:1.25rem;--fontSizeBase600:1.5rem;--fontSizeHero700:1.75rem;--fontSizeHero800:2rem;--fontSizeHero900:2.5rem;
--lineHeightBase200:1rem;--lineHeightBase300:1.25rem;--lineHeightBase400:1.375rem;--lineHeightBase500:1.75rem;--lineHeightBase600:2rem;--lineHeightHero800:2.5rem;--lineHeightHero900:3.25rem;
--fontWeightRegular:400;--fontWeightSemibold:600;
--spacingXXS:2px;--spacingXS:4px;--spacingS:8px;--spacingM:12px;--spacingL:16px;--spacingXL:20px;--spacingXXL:24px;--spacingXXXL:32px;
--borderRadiusSmall:2px;--borderRadiusMedium:4px;--borderRadiusLarge:6px;--borderRadiusXLarge:8px;--borderRadiusCircular:10000px;
--strokeWidthThin:1px;--strokeWidthThick:2px;--strokeWidthThickest:4px;
--shadow4:0 0 2px rgba(0,0,0,.12),0 2px 4px rgba(0,0,0,.14);--shadow8:0 0 2px rgba(0,0,0,.12),0 4px 8px rgba(0,0,0,.14);
--colorNeutralBackground1:#ffffff;--colorNeutralBackground2:#fafafa;--colorNeutralBackground3:#f5f5f5;
--colorNeutralForeground1:#242424;--colorNeutralForeground2:#424242;--colorNeutralForeground3:#616161;--colorNeutralForegroundOnBrand:#ffffff;
--colorNeutralStroke1:#d1d1d1;--colorNeutralStroke2:#e0e0e0;--colorNeutralStrokeAccessible:#616161;
--colorBrandBackground:#0f6cbd;--colorBrandBackgroundHover:#115ea3;--colorBrandBackground2:#ebf3fc;--colorBrandStroke1:#0f6cbd;--colorBrandForeground1:#0f6cbd;--colorBrandForegroundLink:#115ea3;
--colorStrokeFocus1:#ffffff;--colorStrokeFocus2:#000000;
--colorPaletteRedBackground1:#fdf3f4;--colorPaletteRedForeground1:#b10e1c;--colorPaletteRedBorder1:#d13438;
--colorPaletteGreenBackground1:#f1faf1;--colorPaletteGreenForeground1:#0e700e;--colorPaletteGreenBorder1:#107c10;
--colorPaletteYellowBackground1:#fffbe6;--colorPaletteYellowForeground1:#835b00;--colorPaletteYellowBorder1:#c19c00;
--colorPaletteDarkOrangeBackground1:#fdf6f3;--colorPaletteDarkOrangeForeground1:#bc4b09;--colorPaletteDarkOrangeBorder1:#f7630c;
--colorPaletteBlueBackground1:#ebf3fc}
@media (prefers-color-scheme:dark){:root{
--colorNeutralBackground1:#292929;--colorNeutralBackground2:#1f1f1f;--colorNeutralBackground3:#141414;
--colorNeutralForeground1:#ffffff;--colorNeutralForeground2:#d6d6d6;--colorNeutralForeground3:#adadad;
--colorNeutralStroke1:#666666;--colorNeutralStroke2:#525252;--colorNeutralStrokeAccessible:#adadad;
--colorBrandBackground:#115ea3;--colorBrandBackgroundHover:#0f6cbd;--colorBrandBackground2:#082338;--colorBrandStroke1:#479ef5;--colorBrandForeground1:#479ef5;--colorBrandForegroundLink:#479ef5;
--colorStrokeFocus1:#292929;--colorStrokeFocus2:#ffffff;
--colorPaletteRedBackground1:#3f1011;--colorPaletteRedForeground1:#e37d80;--colorPaletteRedBorder1:#dc626d;
--colorPaletteGreenBackground1:#052505;--colorPaletteGreenForeground1:#54b054;--colorPaletteGreenBorder1:#54b054;
--colorPaletteYellowBackground1:#4a3500;--colorPaletteYellowForeground1:#f2c661;--colorPaletteYellowBorder1:#f2c661;
--colorPaletteDarkOrangeBackground1:#411200;--colorPaletteDarkOrangeForeground1:#f98845;--colorPaletteDarkOrangeBorder1:#f98845;
--colorPaletteBlueBackground1:#082338}}
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--colorNeutralBackground1);color:var(--colorNeutralForeground1);font-family:var(--fontFamilyBase);font-size:var(--fontSizeBase300);line-height:var(--lineHeightBase300)}
a{color:var(--colorBrandForegroundLink);text-underline-offset:.2em}
a:hover{text-decoration-thickness:.15em}
:focus-visible{outline:3px solid var(--colorStrokeFocus2);outline-offset:2px;box-shadow:0 0 0 3px var(--colorStrokeFocus1)}
.skip{position:absolute;left:-100vw;top:0;z-index:10;padding:.75rem 1rem;background:var(--colorNeutralBackground1);color:var(--colorNeutralForeground1)}
.skip:focus{left:0}
.visually-hidden{position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
.num{font-variant-numeric:tabular-nums}
body>header{display:flex;flex-wrap:wrap;gap:var(--spacingXS) var(--spacingXXL);align-items:baseline;justify-content:space-between;padding:var(--spacingM) var(--spacingXL);background:var(--colorNeutralBackground3);border-bottom:var(--strokeWidthThin) solid var(--colorNeutralStroke1)}
.brand{margin:0;font-size:var(--fontSizeBase500);line-height:var(--lineHeightBase500);font-weight:var(--fontWeightSemibold)}
.brand a{color:inherit;text-decoration:none}
.who{margin:0;color:var(--colorNeutralForeground2);font-size:var(--fontSizeBase200)}
nav{padding:0 var(--spacingXL);border-bottom:var(--strokeWidthThin) solid var(--colorNeutralStroke1)}
nav ul{display:flex;flex-wrap:wrap;gap:0 var(--spacingXS);margin:0;padding:0;list-style:none}
nav a{display:inline-block;min-height:2.5rem;padding:.6rem var(--spacingM);border-bottom:3px solid transparent;color:var(--colorNeutralForeground1);text-decoration:none}
nav a:hover{background:var(--colorNeutralBackground3)}
nav a[aria-current="page"]{border-bottom-color:var(--colorBrandStroke1);font-weight:var(--fontWeightSemibold)}
main{max-width:46rem;margin:0 auto;padding:var(--spacingXXL) var(--spacingXL)}
main.wide{max-width:70rem}
h1{margin:var(--spacingS) 0 var(--spacingM);font-size:var(--fontSizeHero800);line-height:var(--lineHeightHero800);font-weight:var(--fontWeightSemibold)}
h2{margin:var(--spacingXXL) 0 var(--spacingS);font-size:var(--fontSizeBase500);line-height:var(--lineHeightBase500);font-weight:var(--fontWeightSemibold)}
h3{margin:var(--spacingXL) 0 var(--spacingXS);font-size:var(--fontSizeBase400);line-height:var(--lineHeightBase400);font-weight:var(--fontWeightSemibold)}
p{margin:var(--spacingS) 0}
.lead{font-size:var(--fontSizeBase400);line-height:var(--lineHeightBase400)}
.muted{color:var(--colorNeutralForeground2)}
code,.mono{font-family:var(--fontFamilyMonospace);font-size:.92em;overflow-wrap:anywhere}
.notice{margin:var(--spacingL) 0;padding:var(--spacingM) var(--spacingL);border:var(--strokeWidthThin) solid var(--notice-border,var(--colorNeutralStroke1));border-left-width:.5rem;border-radius:var(--borderRadiusMedium);background:var(--notice-bg,var(--colorNeutralBackground2))}
.notice p,.notice ul{margin:var(--spacingXS) 0}
.notice-title{margin:0 0 var(--spacingXS);font-weight:var(--fontWeightSemibold);font-size:var(--fontSizeBase300)}
.notice.info{--notice-bg:var(--colorPaletteBlueBackground1);--notice-border:var(--colorBrandStroke1)}
.notice.success{--notice-bg:var(--colorPaletteGreenBackground1);--notice-border:var(--colorPaletteGreenBorder1)}
.notice.warning{--notice-bg:var(--colorPaletteYellowBackground1);--notice-border:var(--colorPaletteYellowBorder1)}
.notice.error{--notice-bg:var(--colorPaletteRedBackground1);--notice-border:var(--colorPaletteRedBorder1)}
dl.summary{display:grid;grid-template-columns:minmax(9rem,14rem) 1fr;margin:var(--spacingL) 0;border-top:var(--strokeWidthThin) solid var(--colorNeutralStroke1)}
dl.summary>div{display:contents}
dl.summary dt,dl.summary dd{margin:0;padding:.55rem .75rem .55rem 0;border-bottom:var(--strokeWidthThin) solid var(--colorNeutralStroke1)}
dl.summary dt{font-weight:var(--fontWeightSemibold)}
dl.summary dd{overflow-wrap:anywhere}
.rows{margin:var(--spacingL) 0;padding:0;list-style:none}
.rows>li{padding:var(--spacingM) 0;border-top:var(--strokeWidthThin) solid var(--colorNeutralStroke1)}
.rows>li:last-child{border-bottom:var(--strokeWidthThin) solid var(--colorNeutralStroke1)}
.row-title{margin:0;font-weight:var(--fontWeightSemibold);overflow-wrap:anywhere}
.row-meta{margin:var(--spacingXXS) 0 var(--spacingS);color:var(--colorNeutralForeground2)}
.feed{margin:var(--spacingXS) 0 var(--spacingL);padding-left:1.1rem}
.feed li{margin:var(--spacingXS) 0;overflow-wrap:anywhere}
.strong-line{font-weight:var(--fontWeightSemibold)}
details.more{margin:var(--spacingXXL) 0 0;border:var(--strokeWidthThin) solid var(--colorNeutralStroke1);border-radius:var(--borderRadiusMedium);background:var(--colorNeutralBackground2)}
details.more>summary{display:flex;align-items:center;min-height:2.5rem;padding:var(--spacingS) var(--spacingL);font-weight:var(--fontWeightSemibold);cursor:pointer}
details.more[open]>summary{border-bottom:var(--strokeWidthThin) solid var(--colorNeutralStroke1)}
details.more>div{padding:0 var(--spacingL) var(--spacingL)}
.actions{display:flex;flex-wrap:wrap;gap:var(--spacingM);margin:var(--spacingL) 0}
.actions>*{flex:1 1 14rem;max-width:22rem}
.btn,button{display:inline-flex;align-items:center;justify-content:center;min-height:2.5rem;min-width:8rem;padding:var(--spacingS) var(--spacingL);border:var(--strokeWidthThin) solid var(--colorNeutralStrokeAccessible);border-radius:var(--borderRadiusMedium);background:var(--colorNeutralBackground1);color:var(--colorNeutralForeground1);font:inherit;font-weight:var(--fontWeightSemibold);text-align:center;text-decoration:none;cursor:pointer}
.btn:hover,button:hover{background:var(--colorNeutralBackground3)}
.btn.primary,button.primary{border-color:var(--colorBrandBackground);background:var(--colorBrandBackground);color:var(--colorNeutralForegroundOnBrand)}
.btn.primary:hover,button.primary:hover{background:var(--colorBrandBackgroundHover)}
.btn.secondary,button.secondary{border-color:var(--colorNeutralStrokeAccessible)}
.btn.subtle,button.subtle{border-color:transparent;background:transparent;color:var(--colorBrandForegroundLink)}
.btn.subtle:hover,button.subtle:hover{background:var(--colorBrandBackground2)}
.btn.danger,button.danger{border-color:var(--colorPaletteRedBorder1);color:var(--colorPaletteRedForeground1)}
.btn.sm,button.sm{min-height:2rem;min-width:0;padding:var(--spacingXS) var(--spacingM)}
form{margin:var(--spacingL) 0}
label,legend{display:block;margin:var(--spacingM) 0 var(--spacingXS);font-weight:var(--fontWeightSemibold)}
.hint{margin:var(--spacingXXS) 0 var(--spacingXS);color:var(--colorNeutralForeground2);font-size:var(--fontSizeBase200)}
.field-error{margin:var(--spacingXXS) 0 var(--spacingXS);color:var(--colorPaletteRedForeground1);font-weight:var(--fontWeightSemibold)}
input[type=text],input[type=date],input[type=time],input[type=number],select,textarea{display:block;width:100%;max-width:38rem;min-height:2.25rem;padding:var(--spacingXS) var(--spacingS);border:var(--strokeWidthThin) solid var(--colorNeutralStrokeAccessible);border-radius:var(--borderRadiusMedium);background:var(--colorNeutralBackground1);color:var(--colorNeutralForeground1);font:inherit}
textarea{min-height:6rem;resize:vertical}
.field.error input,.field.error textarea,.field.error select{border:var(--strokeWidthThick) solid var(--colorPaletteRedBorder1)}
fieldset{margin:var(--spacingL) 0;padding:var(--spacingXS) var(--spacingL) var(--spacingL);border:var(--strokeWidthThin) solid var(--colorNeutralStroke1);border-radius:var(--borderRadiusMedium)}
legend{padding:0 var(--spacingXS)}
.choice{display:flex;align-items:center;gap:var(--spacingS);min-height:2.25rem}
.choice input{flex:none;width:1.5rem;height:1.5rem;margin:0}
.choice label{display:inline;margin:0;font-weight:var(--fontWeightRegular)}
.table-wrap{overflow-x:auto;margin:var(--spacingL) 0;border:var(--strokeWidthThin) solid var(--colorNeutralStroke1);border-radius:var(--borderRadiusMedium)}
table{width:100%;min-width:30rem;border-collapse:collapse}
caption{padding:var(--spacingS) var(--spacingM);text-align:left;font-weight:var(--fontWeightSemibold)}
th,td{padding:var(--spacingS) var(--spacingM);border-top:var(--strokeWidthThin) solid var(--colorNeutralStroke2);text-align:left;vertical-align:top;overflow-wrap:break-word}
th{background:var(--colorNeutralBackground3);font-weight:var(--fontWeightSemibold)}
td.r,th.r{text-align:right}
.nw{white-space:nowrap}
td form{margin:0}
td .btn,td button{min-width:0;min-height:2rem;padding:var(--spacingXS) var(--spacingM)}
blockquote.quote{margin:var(--spacingS) 0;padding:var(--spacingS) var(--spacingL);border-left:.375rem solid var(--colorNeutralStrokeAccessible);background:var(--colorNeutralBackground3);overflow-wrap:anywhere}
.quote-label{margin:var(--spacingM) 0 0;color:var(--colorNeutralForeground2);font-size:var(--fontSizeBase200);font-weight:var(--fontWeightSemibold)}
footer{max-width:46rem;margin:var(--spacingXXXL) auto 0;padding:var(--spacingL) var(--spacingXL) var(--spacingXXXL);border-top:var(--strokeWidthThin) solid var(--colorNeutralStroke2);color:var(--colorNeutralForeground3);font-size:var(--fontSizeBase200);line-height:var(--lineHeightBase200)}
main.wide+footer{max-width:70rem}
footer p{margin:0}
footer details{margin-top:var(--spacingXS)}
footer summary{display:inline-block;cursor:pointer;color:var(--colorBrandForegroundLink)}
footer details p{margin-top:var(--spacingXS);max-width:46rem}
.head{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:var(--spacingS) var(--spacingXL);margin:0 0 var(--spacingXL)}
.head h1{margin:0}
.head p{margin:var(--spacingXS) 0 0;color:var(--colorNeutralForeground2)}
.seg{display:inline-flex;align-items:center;border:var(--strokeWidthThin) solid var(--colorNeutralStrokeAccessible);border-radius:var(--borderRadiusMedium);overflow:hidden}
.seg>span{padding:0 var(--spacingM);color:var(--colorNeutralForeground2)}
.seg a{display:inline-flex;align-items:center;min-height:2rem;padding:0 var(--spacingM);border-left:var(--strokeWidthThin) solid var(--colorNeutralStroke1);color:var(--colorNeutralForeground1);font-weight:var(--fontWeightSemibold);text-decoration:none}
.seg a:hover{background:var(--colorNeutralBackground3)}
.seg a[aria-current="true"]{background:var(--colorBrandBackground2);color:var(--colorBrandForegroundLink)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(12rem,1fr));gap:var(--spacingL);margin:0 0 var(--spacingXXL);padding:0;list-style:none}
.kpi{padding:var(--spacingL) var(--spacingXL);background:var(--colorNeutralBackground2);border:var(--strokeWidthThin) solid var(--colorNeutralStroke2);border-radius:var(--borderRadiusXLarge)}
.kpi .k{margin:0;color:var(--colorNeutralForeground2);font-size:var(--fontSizeBase200);line-height:var(--lineHeightBase200);font-weight:var(--fontWeightSemibold)}
.kpi .v{margin:var(--spacingXS) 0 0;font-size:var(--fontSizeHero800);line-height:var(--lineHeightHero800);font-weight:var(--fontWeightSemibold);font-variant-numeric:tabular-nums}
.kpi .v small,.fig small{font-size:var(--fontSizeBase400);font-weight:var(--fontWeightRegular);color:var(--colorNeutralForeground2)}
.kpi .n{margin:var(--spacingXS) 0 0;color:var(--colorNeutralForeground2);font-size:var(--fontSizeBase200);line-height:var(--lineHeightBase200)}
.kpi.good .v{color:var(--colorPaletteGreenForeground1)}
.sec{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:var(--spacingXS) var(--spacingXL);margin:var(--spacingXXXL) 0 var(--spacingM)}
.sec h2{margin:0}
.sec p{margin:0;color:var(--colorNeutralForeground2)}
.focus{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:var(--spacingXXL);padding:var(--spacingXXL);background:var(--colorNeutralBackground1);border:var(--strokeWidthThin) solid var(--colorNeutralStroke2);border-left:var(--strokeWidthThickest) solid var(--colorBrandStroke1);border-radius:var(--borderRadiusXLarge);box-shadow:var(--shadow4)}
.eyebrow{display:flex;align-items:center;gap:var(--spacingS);margin:0;color:var(--colorBrandForegroundLink);font-size:var(--fontSizeBase300);line-height:var(--lineHeightBase300);font-weight:var(--fontWeightSemibold)}
.focus h3{margin:var(--spacingS) 0 var(--spacingXS);font-size:var(--fontSizeBase600);line-height:var(--lineHeightBase600);overflow-wrap:anywhere}
.m{margin:0;color:var(--colorNeutralForeground2);font-size:var(--fontSizeBase200);line-height:var(--lineHeightBase200)}
.fig{margin:var(--spacingL) 0 0;font-size:var(--fontSizeHero900);line-height:var(--lineHeightHero900);font-weight:var(--fontWeightSemibold);font-variant-numeric:tabular-nums;color:var(--colorNeutralForeground1)}
.fig.save{color:var(--colorPaletteGreenForeground1)}
.figsub{margin:0 0 var(--spacingM);color:var(--colorNeutralForeground2)}
.chips{display:flex;flex-wrap:wrap;gap:var(--spacingS);margin:var(--spacingM) 0}
.facts{display:grid;grid-template-columns:max-content 1fr;gap:var(--spacingS) var(--spacingL);margin:var(--spacingL) 0}
.facts dt{color:var(--colorNeutralForeground2);font-weight:var(--fontWeightSemibold)}
.facts dd{margin:0}
.focus>.facts{grid-column:1/-1;margin:0}
.acts{display:flex;flex-wrap:wrap;gap:var(--spacingM);margin:var(--spacingL) 0 0}
.acts.stack{flex-direction:column}
.acts.stack>*{width:100%}
.chart{margin:0 0 var(--spacingL)}
.chart:last-child{margin-bottom:0}
.chart figcaption{display:flex;flex-wrap:wrap;justify-content:space-between;gap:0 var(--spacingM);margin:0 0 var(--spacingXS);font-weight:var(--fontWeightSemibold)}
.chart figcaption span{color:var(--colorNeutralForeground2);font-weight:var(--fontWeightRegular)}
.chart svg{display:block;width:100%;height:auto}
.gl{stroke:var(--colorNeutralStroke2);stroke-width:1}
.ax{fill:var(--colorNeutralForeground3);font-size:.6875rem;font-family:var(--fontFamilyBase)}
.ln{fill:none;stroke:var(--colorBrandForeground1);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.ar{fill:var(--colorBrandBackground2)}
.dt{fill:var(--colorBrandForeground1)}
.thr{stroke:var(--colorPaletteDarkOrangeBorder1);stroke-width:1.5;stroke-dasharray:4 3}
.thr-t{fill:var(--colorPaletteDarkOrangeForeground1);font-size:.6875rem;font-family:var(--fontFamilyBase)}
.items{display:grid;gap:var(--spacingS);margin:0;padding:0;list-style:none}
.focus+.items{margin-top:var(--spacingM)}
.item{display:grid;grid-template-columns:2rem minmax(0,1fr) 10rem 7.5rem 6rem;grid-template-areas:"rank main impact spark act";align-items:center;gap:var(--spacingM) var(--spacingL);padding:var(--spacingM) var(--spacingL);background:var(--colorNeutralBackground1);border:var(--strokeWidthThin) solid var(--colorNeutralStroke2);border-radius:var(--borderRadiusXLarge)}
.item:hover{border-color:var(--colorNeutralStroke1);box-shadow:var(--shadow4)}
.rank{grid-area:rank;display:grid;place-items:center;width:2rem;height:2rem;border-radius:var(--borderRadiusCircular);background:var(--colorNeutralBackground3);color:var(--colorNeutralForeground2);font-weight:var(--fontWeightSemibold);font-variant-numeric:tabular-nums}
.rank.first{background:var(--colorBrandBackground);color:var(--colorNeutralForegroundOnBrand)}
.main{grid-area:main;min-width:0}
.main .t,.main .m{display:block}
.main .t{margin:0;font-weight:var(--fontWeightSemibold);overflow-wrap:anywhere}
.main .m{margin:var(--spacingXXS) 0 var(--spacingXS)}
.main .chips{margin:0}
.impact{grid-area:impact;text-align:right;font-variant-numeric:tabular-nums}
.impact .lab{display:block;color:var(--colorNeutralForeground2);font-size:var(--fontSizeBase200);line-height:var(--lineHeightBase200)}
.impact .y{display:block;font-size:var(--fontSizeBase500);line-height:var(--lineHeightBase500);font-weight:var(--fontWeightSemibold)}
.impact .y small{font-size:var(--fontSizeBase200);font-weight:var(--fontWeightRegular);color:var(--colorNeutralForeground2)}
.impact .mo{display:block;color:var(--colorNeutralForeground2);font-size:var(--fontSizeBase200);line-height:var(--lineHeightBase200)}
.impact.save .y{color:var(--colorPaletteGreenForeground1)}
.impact.cost .y{color:var(--colorNeutralForeground1)}
.impact.none .y{color:var(--colorNeutralForeground3)}
.bar{display:block;width:100%;height:4px;margin-top:var(--spacingXS)}
.bt{fill:var(--colorNeutralStroke2)}
.bv{fill:var(--colorBrandForeground1)}
.save .bv{fill:var(--colorPaletteGreenBorder1)}
.spark{grid-area:spark;min-width:0}
svg.sp{display:block;width:100%;height:32px}
.sp .ln{stroke-width:1.5}
.sp.none .ln{stroke:var(--colorNeutralStrokeAccessible);stroke-dasharray:3 3}
.act{grid-area:act;text-align:right}
.chip{display:inline-flex;align-items:center;gap:var(--spacingXS);padding:1px var(--spacingS);border:var(--strokeWidthThin) solid var(--chip-b,var(--colorNeutralStrokeAccessible));border-radius:var(--borderRadiusCircular);background:var(--chip-bg,var(--colorNeutralBackground1));color:var(--chip-fg,var(--colorNeutralForeground2));font-size:var(--fontSizeBase200);line-height:var(--lineHeightBase200);font-weight:var(--fontWeightSemibold);white-space:nowrap}
.chip svg{width:12px;height:12px;fill:currentColor}
.chip.low{--chip-bg:var(--colorPaletteGreenBackground1);--chip-fg:var(--colorPaletteGreenForeground1);--chip-b:var(--colorPaletteGreenBorder1)}
.chip.mid{--chip-bg:var(--colorPaletteDarkOrangeBackground1);--chip-fg:var(--colorPaletteDarkOrangeForeground1);--chip-b:var(--colorPaletteDarkOrangeBorder1)}
.chip.high{--chip-bg:var(--colorPaletteRedBackground1);--chip-fg:var(--colorPaletteRedForeground1);--chip-b:var(--colorPaletteRedBorder1)}
.chip.info{--chip-bg:var(--colorBrandBackground2);--chip-fg:var(--colorBrandForegroundLink);--chip-b:var(--colorBrandStroke1)}
details.grp{background:var(--colorNeutralBackground1);border:var(--strokeWidthThin) solid var(--colorNeutralStroke2);border-radius:var(--borderRadiusXLarge)}
details.grp[open]{border-color:var(--colorNeutralStroke1);box-shadow:var(--shadow4)}
details.grp>summary{list-style:none;cursor:pointer}
details.grp>summary::-webkit-details-marker{display:none}
details.grp>summary.item{border:0;background:transparent;box-shadow:none}
details.grp .when-open,details.grp[open] .when-closed{display:none}
details.grp[open] .when-open{display:inline}
.members{padding:0 var(--spacingL) var(--spacingL)}
.members .table-wrap{margin:0}
.members table{min-width:24rem}
.quiet{color:var(--colorNeutralForeground3)}
.recent{margin:0;padding:0;list-style:none}
.recent li{display:flex;flex-wrap:wrap;align-items:baseline;gap:var(--spacingXS) var(--spacingM);padding:var(--spacingS) 0;border-top:var(--strokeWidthThin) solid var(--colorNeutralStroke2)}
.recent li:first-child{border-top:0}
.cols{display:grid;grid-template-columns:minmax(0,1fr) 22rem;gap:var(--spacingXXL);align-items:start;margin-top:var(--spacingXXL)}
.cols.solo{grid-template-columns:minmax(0,46rem)}
.cols>div>h2:first-child{margin-top:0}
.panel{padding:var(--spacingXL);background:var(--colorNeutralBackground2);border:var(--strokeWidthThin) solid var(--colorNeutralStroke2);border-radius:var(--borderRadiusXLarge)}
.panel h2{margin-top:0}
.panel form{margin:0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(20rem,100%),1fr));gap:var(--spacingL);align-items:start;margin:var(--spacingL) 0}
@media (max-width:64rem){
.cols,.cols.solo{grid-template-columns:1fr}
}
@media (max-width:52rem){
.focus{grid-template-columns:1fr}
.item{grid-template-columns:2rem minmax(0,1fr) auto;grid-template-areas:"rank main impact" "rank spark act"}
}
@media (max-width:40em){
main{padding:var(--spacingL)}
dl.summary{grid-template-columns:1fr}
dl.summary dt{padding-bottom:0;border-bottom:0}
.actions{flex-direction:column}
.actions>*{flex:none;width:100%;max-width:none}
.btn,button{width:100%}
td .btn,td button,.btn.sm{width:auto}
.item{grid-template-columns:2rem minmax(0,1fr);grid-template-areas:"rank main" "rank impact" "rank spark" "rank act"}
.impact,.act{text-align:left}
.focus{padding:var(--spacingL)}
.facts{grid-template-columns:1fr}
}
@media (forced-colors:active){
a{color:LinkText}
.btn,button{border:2px solid ButtonText;background:ButtonFace;color:ButtonText}
.btn.primary,button.primary{border-color:Highlight}
.notice,blockquote.quote,.table-wrap,th,td,details.more,details.grp,.item,.kpi,.focus,.panel,.chip{border-color:CanvasText}
nav a[aria-current="page"]{border-bottom-color:Highlight}
:focus-visible{outline:3px solid Highlight;box-shadow:none}
.ln{stroke:Highlight}
.dt,.bv{fill:Highlight}
.bt{fill:GrayText}
.gl{stroke:GrayText}
}
"""
