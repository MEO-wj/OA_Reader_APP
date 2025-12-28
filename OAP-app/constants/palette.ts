export type Palette = {
  surface: string;
  surfaceWarm: string;
  gold50: string;
  gold100: string;
  cardTint: string;
  gold200: string;
  gold300: string;
  gold400: string;
  gold500: string;
  gold600: string;
  warm100: string;
  rose100: string;
  imperial50: string;
  imperial100: string;
  imperial400: string;
  imperial500: string;
  imperial600: string;
  stone900: string;
  stone850: string;
  stone800: string;
  stone700: string;
  stone600: string;
  stone500: string;
  stone400: string;
  stone300: string;
  stone200: string;
  stone100: string;
  white: string;
};

export const lightColors: Palette = {
  surface: '#FDFCF8',
  surfaceWarm: '#FFF8ED',
  gold50: '#FBF7E8',
  gold100: '#F5EBC9',
  cardTint: '#F7F4EF',
  gold200: '#F3E0AF',
  gold300: '#E8C871',
  gold400: '#D4AF37',
  gold500: '#B8860B',
  gold600: '#926F34',
  warm100: '#FDEED6',
  rose100: '#F9D7D7',
  imperial50: '#FCECEC',
  imperial100: '#F7CFCF',
  imperial400: '#E16C6C',
  imperial500: '#C02425',
  imperial600: '#9B1C1C',
  stone900: '#1C1917',
  stone850: '#1C1917',
  stone800: '#2B211E',
  stone700: '#3A2F2B',
  stone600: '#5C524E',
  stone500: '#6B6461',
  stone400: '#9A928F',
  stone300: '#C8C2BF',
  stone200: '#E6E2DF',
  stone100: '#F1EFED',
  white: '#FFFFFF',
};

export const darkColors: Palette = {
  surface: '#0F1115',
  surfaceWarm: '#12141A',
  gold50: '#2A2413',
  gold100: '#3A3117',
  cardTint: '#171A21',
  gold200: '#5A4A1E',
  gold300: '#E8C871',
  gold400: '#D4AF37',
  gold500: '#B8860B',
  gold600: '#926F34',
  warm100: '#2A2317',
  rose100: '#2D1B1C',
  imperial50: '#2A1414',
  imperial100: '#3B1B1B',
  imperial400: '#E16C6C',
  imperial500: '#C02425',
  imperial600: '#FF8585',
  stone900: '#F6F2EE',
  stone850: '#E8E2DB',
  stone800: '#D7D0C8',
  stone700: '#BDB5AE',
  stone600: '#A39B94',
  stone500: '#8A827C',
  stone400: '#6F6863',
  stone300: '#514B47',
  stone200: '#332E2B',
  stone100: '#24201E',
  white: '#141312',
};

export function getPalette(colorScheme: 'light' | 'dark' | null | undefined): Palette {
  return colorScheme === 'dark' ? darkColors : lightColors;
}

// Backwards compatible: legacy code assumes this is the light palette.
export const colors = lightColors;
