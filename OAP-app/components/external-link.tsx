import { Href, Link } from 'expo-router';
import { openBrowserAsync, WebBrowserPresentationStyle } from 'expo-web-browser';
import { type ComponentProps } from 'react';

type Props = Omit<ComponentProps<typeof Link>, 'href'> & { href: Href & string };

export function ExternalLink({ href, ...rest }: Props) {
  const isStandalone =
    typeof window !== 'undefined' &&
    ((window.matchMedia?.('(display-mode: standalone)')?.matches ?? false) ||
      (navigator as Navigator & { standalone?: boolean }).standalone === true);

  return (
    <Link
      target={isStandalone ? '_self' : '_blank'}
      {...rest}
      href={href}
      onPress={async (event) => {
        if (process.env.EXPO_OS !== 'web') {
          event.preventDefault();
          await openBrowserAsync(href, {
            presentationStyle: WebBrowserPresentationStyle.AUTOMATIC,
          });
        }
      }}
    />
  );
}
