"""Fence's single stylesheet, scoped to the Streamlit shell."""

STYLES = """<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght,SOFT@9..144,600..700,0..100&family=Hanken+Grotesk:wght@400..600&display=swap');

:root {
    --base: #0F1A33;
    --glow-violet: #2A2E73;
    --glow-teal: #1F6F78;
    --glass: rgba(255,255,255,.08);
    --glass-strong: rgba(255,255,255,.14);
    --glass-border: rgba(255,255,255,.18);
    --safe: #7FD6C2;
    --warn: #F2B84B;
    --danger: #F0766B;
    --text: #E8ECF8;
    --text-dim: #9AA6C7;
    --raised: inset 0 1px 0 rgba(255,255,255,.12), 0 24px 60px -24px rgba(5,10,30,.7);
    --nav-height: 68px;
    --heading: 'Fraunces', Georgia, serif;
    --body: 'Hanken Grotesk', system-ui, sans-serif;
}

.stApp { background: var(--base); color: var(--text); }
.stApp::before, .stApp::after {
    content: ''; position: fixed; inset: 0; pointer-events: none;
}
.stApp::before {
    background: radial-gradient(ellipse at 6% 12%, var(--glow-violet), transparent 55%),
                radial-gradient(ellipse at 91% 46%, #1f6f7899, transparent 48%),
                radial-gradient(ellipse at 61% 106%, #f2b84b15, transparent 47%);
    filter: blur(42px); opacity: .75; animation: fence-drift 70s ease-in-out infinite alternate;
}
.stApp::after {
    background: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.84' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' opacity='1' filter='url(%23n)'/%3E%3C/svg%3E");
    opacity: .04;
}
@keyframes fence-drift { to { transform: translate3d(-3%, 4%, 0) scale(1.08); } }
@keyframes fence-arrive { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

[data-testid='stHeader'], [data-testid='stToolbar'], [data-testid='stDecoration'], #MainMenu,
[data-testid='stHeaderActionElements'] { display: none !important; }
.stMainBlockContainer {
    position: relative; z-index: 1; max-width: 1250px;
    padding: var(--nav-height) 36px 52px;
}
.stApp, .stApp p, .stApp label, .stApp button, .stApp textarea,
.stApp [data-baseweb='select'], [data-baseweb='popover'] { font-family: var(--body); }
.stApp p, .stApp li { line-height: 1.6; }
.stApp h1, .stApp h2, .stApp h3 {
    font-family: var(--heading); font-weight: 650; font-optical-sizing: auto;
    font-variation-settings: 'SOFT' 65; letter-spacing: -.04em; color: var(--text);
}
.stApp a { color: var(--safe); text-underline-offset: 4px; }
.stApp :is(a, button, textarea, input, [role='combobox']):focus-visible,
.stApp [data-baseweb='select']:has([role='combobox']:focus-visible),
.stApp [data-testid='stExpander']:has(summary:focus-visible) {
    outline: 2px solid var(--safe) !important; outline-offset: 2px;
}
.stApp [data-testid='stExpander']:has(summary:focus-visible) { border-radius: 14px; }
.stApp :is(h2[id], h3[id], .fence-anchor) { scroll-margin-top: calc(var(--nav-height) + 24px); }
.fence-anchor { display: block; height: 0; }

.fence-nav {
    position: fixed; inset: 0 0 auto; z-index: 50; min-height: var(--nav-height);
    background: rgba(15,26,51,.91); border-bottom: 1px solid var(--glass-border);
    backdrop-filter: blur(22px) saturate(140%); box-shadow: 0 12px 42px rgba(5,10,30,.18);
}
.fence-nav-inner {
    max-width: 1250px; padding: 0 36px; margin: auto; min-height: var(--nav-height);
    display: flex; align-items: center; justify-content: space-between; gap: 16px;
}
.fence-nav a { text-decoration: none; }
.fence-nav .fence-brand {
    display: inline-flex; align-items: center; gap: 8px; font-family: var(--heading);
    font-size: 28px; font-weight: 700; letter-spacing: -.04em; color: var(--text);
}
.fence-brand svg, .fence-brand span { color: var(--safe); }
.fence-brand span { margin-left: -7px; }
.fence-nav nav { display: flex; align-items: center; gap: clamp(12px, 2vw, 28px); }
.fence-nav nav a { color: var(--text-dim); font-size: 14px; font-weight: 600; padding: 9px 0; }
.fence-nav nav a:hover { color: var(--safe); }

.st-key-fence-hero {
    position: relative; min-height: calc(100svh - var(--nav-height)); padding: 32px 0 56px;
    justify-content: center; animation: fence-arrive 500ms ease-out both;
}
.st-key-fence-hero > [data-testid='stVerticalBlock'] { justify-content: center; }
.fence-hero-copy { max-width: 690px; }
.fence-kicker {
    display: inline-flex; align-items: center; gap: 8px; margin: 0 0 16px;
    border: 1px solid var(--glass-border); border-radius: 999px; padding: 4px 12px;
    background: rgba(15,26,51,.45); color: var(--text); font-size: 14px; font-weight: 600;
}
.fence-kicker span { width: 7px; height: 7px; border-radius: 50%; background: var(--safe); box-shadow: 0 0 14px var(--safe); }
.stApp .fence-hero-copy h1 { font-size: 72px; line-height: 1.02; padding: 0; margin: 0 0 20px; }
.stApp .fence-intro { font-size: 20px; color: var(--text-dim); max-width: 52ch; margin: 0 0 12px; }
.st-key-fence-proposal-panel, .fence-preview, .fence-stat {
    border: 1px solid var(--glass-border); box-shadow: var(--raised);
    backdrop-filter: blur(22px) saturate(140%);
    background: linear-gradient(148deg, var(--glass-strong), var(--glass)), rgba(15,26,51,.72);
}
.st-key-fence-proposal-panel { padding: 20px; border-radius: 28px; position: relative; z-index: 2; }
.stApp [data-testid='stCaptionContainer'] { opacity: 1; }
.stApp [data-testid='stCaptionContainer'] p {
    color: color-mix(in srgb, var(--text-dim), var(--text) 40%); font-size: 14px;
}
.stApp [data-testid='stWidgetLabel'] p { color: var(--text); font-weight: 600; font-size: 16px; }
.stApp [data-baseweb='textarea'], .stApp [data-baseweb='select'] > div {
    border-radius: 14px; background: rgba(10,19,38,.72); border: 1px solid var(--glass-border);
    color: var(--text); transition: background-color 200ms ease-out, border-color 200ms ease-out;
}
.stApp [data-baseweb='textarea']:focus-within, .stApp [data-baseweb='select'] > div:focus-within {
    background: #1c2b48; border-color: var(--safe);
}
.stApp textarea { background: transparent; color: var(--text); font-size: 16px; }
.stApp textarea::placeholder { color: var(--text-dim); opacity: 1; }
.stApp [data-testid='stButton'] button {
    min-height: 48px; border-radius: 14px; font-weight: 600;
    transition: background-color 200ms ease-out, border-color 200ms ease-out, color 200ms ease-out;
}
.stApp [data-testid='stBaseButton-primary'] { background: var(--safe); border-color: var(--safe); color: #0b2230; }
.stApp [data-testid='stBaseButton-primary']:hover { background: #a2e9d9; border-color: #a2e9d9; color: #0b2230; }
.stApp [data-testid='stBaseButton-secondary'] { background: var(--glass); border-color: var(--glass-border); color: var(--text); }
.stApp [data-testid='stBaseButton-secondary']:hover { background: var(--glass-strong); border-color: var(--safe); color: var(--text); }

.fence-preview {
    position: relative; margin: 52px 24px 0 -72px; padding: 28px; border-radius: 28px;
    background: linear-gradient(155deg, #233855ee, #14233de8);
}
.fence-preview::before, .fence-preview::after {
    content: ''; position: absolute; z-index: -1; pointer-events: none; border-radius: 28px;
    border: 1px solid rgba(127,214,194,.21); inset: 12px -13px -13px 12px;
}
.fence-preview::after { inset: 24px -24px -24px 24px; opacity: .48; }
.fence-preview-head { display: flex; align-items: center; gap: 10px; color: var(--text); font-weight: 600; }
.fence-archive-icon { color: var(--safe); background: #7fd6c21a; display: grid; place-items: center; width: 38px; height: 38px; border-radius: 12px; }
.fence-archive-icon svg { width: 23px; height: 23px; }
.fence-preview-date { margin-left: auto; color: var(--text-dim); font-size: 14px; }
.fence-preview figcaption { margin-top: 28px; }
.fence-meta, .fence-count, .fence-footer { font-size: 14px; color: var(--text-dim); }
.stApp .fence-preview h2 { margin: 4px 0 16px; padding: 0; font-size: 44px; line-height: 1.08; }
.stApp .fence-preview-outcome {
    padding: 14px 0; border-top: 1px solid var(--glass-border); border-bottom: 1px solid var(--glass-border);
    color: var(--danger); font-family: var(--heading) !important; font-size: 28px; margin-bottom: 14px;
}
.fence-preview-outcome span { color: var(--text); font-family: var(--body); font-size: 16px; margin-left: 5px; }
.fence-preview-reason { color: var(--text-dim); font-size: 16px; margin: 0 0 14px; }
.fence-preview a { font-size: 14px; font-weight: 600; }

.st-key-fence-problem, .st-key-fence-archive, .fence-how {
    border-top: 1px solid var(--glass-border); padding: 52px 0 30px; margin-top: 28px;
}
.stApp .fence-section-title { font-size: 44px; line-height: 1.1; padding: 0; margin: 0 0 8px; }
.stApp .fence-section-lede { font-size: 20px; color: var(--text-dim); max-width: 65ch; margin-bottom: 14px; }
.fence-beats p { max-width: 62ch; margin: 0; padding: 12px 0; border-bottom: 1px solid #ffffff12; color: var(--text-dim); }
.fence-beats strong { color: var(--text); font-weight: 600; }
.fence-stat { padding: 25px 28px; margin: 0; border-radius: 20px; }
.fence-stat strong { display: block; font: 650 72px/.98 var(--heading); letter-spacing: -.05em; color: var(--danger); margin: 12px 0; }
.fence-stat p { font-size: 20px; margin: 0 0 14px; }
.fence-stat figcaption { font-size: 14px; color: var(--text-dim); }

.st-key-fence-archive [data-testid='stButton'] { width: fit-content; }
.st-key-fence-timeline { padding-left: 21px; position: relative; }
.st-key-fence-timeline::before { content: ''; position: absolute; left: 5px; top: 24px; bottom: 24px; width: 1px; background: var(--glass-border); }
.st-key-fence-timeline [class*='st-key-archive-'] { position: relative; --outcome: var(--text-dim); }
.st-key-fence-timeline [class*='st-key-archive-success-'] { --outcome: var(--safe); }
.st-key-fence-timeline [class*='st-key-archive-partial-'] { --outcome: var(--warn); }
.st-key-fence-timeline :is([class*='st-key-archive-failed-'], [class*='st-key-archive-rolled_back-']) { --outcome: var(--danger); }
.st-key-fence-timeline [class*='st-key-archive-']::before {
    content: ''; position: absolute; top: 22px; left: -20px; width: 9px; height: 9px;
    border: 2px solid var(--base); border-radius: 50%; background: var(--outcome); box-sizing: content-box;
}
.stApp [data-testid='stExpander'] details { border: 1px solid var(--glass-border); border-radius: 14px; background: rgba(20,34,60,.88); }
.stApp [data-testid='stExpander'] summary { min-height: 52px; border-radius: 14px; transition: background-color 200ms ease-out; }
.stApp [data-testid='stExpander'] summary:hover { background: var(--glass); }
.st-key-fence-timeline summary [data-testid='stMarkdownContainer'] span { color: var(--outcome) !important; }
.fence-decision-detail { color: var(--text-dim); padding: 4px 4px 0; overflow-wrap: anywhere; }
.fence-decision-detail dt { color: var(--text); font-weight: 600; margin-top: 12px; }
.fence-decision-detail dd { margin: 2px 0 0; max-width: 72ch; }
.fence-decision-detail ul { margin: 3px 0 0; }
.fence-decision-detail .fence-chips { display: flex; flex-wrap: wrap; gap: 6px; padding: 0; margin: 16px 0 6px; list-style: none; }
.fence-chip { border: 1px solid var(--glass-border); border-radius: 999px; padding: 2px 9px; font-size: 14px; }

.fence-steps, .fence-planned { display: grid; gap: 12px; margin: 20px 0; padding: 0; list-style: none; }
.fence-steps { grid-template-columns: repeat(3, 1fr); }
.fence-planned { grid-template-columns: 1fr 1fr; }
.fence-steps li, .fence-planned section {
    border: 1px solid var(--glass-border); border-radius: 20px; padding: 16px 20px; background: rgba(15,26,51,.68);
}
.fence-steps strong { font: 650 24px var(--heading); color: var(--safe); }
.fence-steps p, .fence-planned p { color: var(--text-dim); margin: 4px 0 0; }
.fence-planned h3 { font-size: 20px; padding: 0; margin: 0; }
.fence-footer { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; margin-top: 34px; }

@media (max-width: 900px) {
    .stApp [data-testid='stHorizontalBlock'] { flex-direction: column; gap: 12px; }
    .stApp [data-testid='stHorizontalBlock'] > [data-testid='stColumn'] { width: 100% !important; flex: 1 1 100%; min-width: 0; }
    .stApp .fence-hero-copy h1 { font-size: 40px; }
    .fence-preview { margin: 10px 12px 16px 0; max-width: 560px; }
    .st-key-fence-hero { min-height: 0; padding-top: 24px; }
    .fence-steps, .fence-planned { grid-template-columns: 1fr; }
}
@media (max-width: 600px) {
    :root { --nav-height: 96px; }
    .stMainBlockContainer { padding: var(--nav-height) 17px 28px; }
    .fence-nav-inner { flex-direction: column; gap: 0; justify-content: center; padding: 3px 10px; }
    .fence-nav nav { justify-content: center; gap: 9px; flex-wrap: wrap; }
    .fence-nav nav a { font-size: 12px; padding: 6px 0; }
    .stApp :is(.fence-intro, .fence-section-lede) { font-size: 16px; }
    .stApp .fence-section-title, .stApp .fence-preview h2 { font-size: 32px; }
    .st-key-fence-proposal-panel { padding: 15px; }
    .fence-preview, .fence-stat { padding: 20px; }
    .fence-preview::after { inset: 17px -15px -15px 17px; }
    .st-key-fence-problem, .st-key-fence-archive, .fence-how { padding-top: 36px; }
}
@media (prefers-reduced-motion: reduce) {
    .stApp::before, .st-key-fence-hero { animation: none; }
    .stApp *, .stApp *::before, .stApp *::after { transition-duration: 0s !important; scroll-behavior: auto !important; }
}
.st-key-fence-baseline, .st-key-fence-grounded, .fence-loading {
    border: 1px solid var(--glass-border); border-radius: 28px; padding: 24px;
    background: rgba(15,26,51,.8); overflow-wrap: anywhere;
}
.st-key-fence-grounded { border-color: var(--safe); background: linear-gradient(145deg, #203c4b, #17263e); box-shadow: var(--raised); }
.fence-risk { display: inline-block; border: 1px solid var(--warn); color: var(--warn); border-radius: 999px; padding: 4px 14px; font-weight: 600; }
.fence-risk-high { color: #0f1a33; background: var(--warn); }
.fence-risk-low { color: var(--safe); border-color: var(--safe); }
.fence-evidence { display: flex; flex-wrap: wrap; gap: 12px; justify-content: space-between; }
.fence-evidence.cited { border-left: 3px solid var(--safe); padding-left: 12px; color: var(--safe); }
.fence-evidence span { font-size: 14px; }
.fence-citation, .stApp [data-testid='stMarkdownContainer'] p { overflow-wrap: anywhere; }
.fence-loading div { height: 22px; margin-top: 16px; border-radius: 10px; background: linear-gradient(90deg, #ffffff08, #ffffff22, #ffffff08); background-size: 200% 100%; animation: fence-shimmer 2.4s ease-in-out infinite; }
.fence-loading div:last-child { width: 65%; }
@keyframes fence-shimmer { to { background-position: -200% 0; } }
@media (max-width: 600px) { .st-key-fence-baseline, .st-key-fence-grounded { padding: 18px; } }
@media (prefers-reduced-motion: reduce) { .fence-loading div { animation: none; } }
</style>"""
