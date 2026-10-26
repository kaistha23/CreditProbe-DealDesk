// Offline builds (a container whose egress denies fonts.googleapis.com): NEXT_FONT_GOOGLE_MOCKED_RESPONSES points
// here, and each Google font the layout asks for is served from a local Liberation font (var/fonts). Used only by
// the cloud session's `next build`; the Mac fetches the real fonts. Nothing in the app changes.
const path = require("path");
const fonts = path.resolve(__dirname, "..", "var", "fonts");
const face = (family, file, weights) => weights.map((w) => `@font-face {
  font-family: '${family}';
  font-style: normal;
  font-weight: ${w};
  font-display: swap;
  src: url(${path.join(fonts, file)}) format('truetype');
}`).join("\n");
module.exports = {
  "https://fonts.googleapis.com/css2?family=Geist:wght@100..900&display=swap": face("Geist", "LiberationSans-Regular.ttf", ["100 900"]),
  "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap": face("JetBrains Mono", "LiberationMono-Regular.ttf", [400, 500, 600]),
  "https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600&display=swap": face("Plus Jakarta Sans", "LiberationSans-Regular.ttf", [400, 500, 600]),
  "https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap": face("Space Grotesk", "LiberationSans-Regular.ttf", [400, 500, 600, 700]),
};
