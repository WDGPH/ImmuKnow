import cedarLogo from "./assets/cedar-ridge.png";
import annieSignature from "./assets/dr-annie-body-signature.png";
import philSignature from "./assets/dr-phil-better-signature.png";
import trilliumLogo from "./assets/trillium-valley.png";
import { settingValue, updateQRStyle, updateThemeSettings } from "./theme-settings";

export const healthUnits = [
  {
    id: "cedar-ridge",
    name: "Cedar Ridge",
    logo: cedarLogo,
    signature: annieSignature,
    signatory: "Dr. Annie Body",
    font: "FreeSerif",
    heading: "#173e31",
    link: "#173e31",
    accent: "#637c50",
    shape: "rounded",
  },
  {
    id: "trillium-valley",
    name: "Trillium Valley",
    logo: trilliumLogo,
    signature: philSignature,
    signatory: "Dr. Phil Better",
    font: "FreeSans",
    heading: "#034770",
    link: "#034770",
    accent: "#26783b",
    shape: "dots",
  },
] as const;
export type HealthUnit = (typeof healthUnits)[number];
export function themedSettings(bytes: Uint8Array, unit: HealthUnit): Uint8Array {
  const images: Record<string, string> = {};
  for (const name of ["logo", "signature"]) {
    const expression = settingValue(bytes, name);
    if (!expression || !/^image\("[^"\r\n]+"/.test(expression))
      throw new Error(`Edit ${name} in Settings before using a theme starter.`);
    images[name] = expression.replace(/^image\("[^"\r\n]+"/, `image("assets/${name}.png"`);
  }
  return updateQRStyle(
    updateThemeSettings(bytes, {
      ...images,
      "signature-name": JSON.stringify(unit.signatory),
      "health-unit-name": JSON.stringify(`${unit.name} Health Unit`),
      "body-font": JSON.stringify(unit.font),
      "heading-color": `rgb("${unit.heading}")`,
      "link-color": `rgb("${unit.link}")`,
      "accent-color": `rgb("${unit.accent}")`,
    }),
    unit.shape,
  );
}
