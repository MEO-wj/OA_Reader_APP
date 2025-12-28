import { useMemo } from 'react';

import { getPalette, type Palette } from '@/constants/palette';
import { useColorScheme } from '@/hooks/use-color-scheme';

export function usePalette(): Palette {
  const scheme = useColorScheme() ?? 'light';
  return useMemo(() => getPalette(scheme), [scheme]);
}

