
import { useEffect, useState } from 'react';

const MERMAID_SCRIPT_URL = 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js';

export function useMermaidScript() {
  const [mermaidScript, setMermaidScript] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    const loadMermaid = async () => {
      try {
        const response = await fetch(MERMAID_SCRIPT_URL);
        if (!response.ok) {
          throw new Error(`Failed to fetch Mermaid script: ${response.status}`);
        }
        const script = await response.text();
        if (mounted) {
          setMermaidScript(script);
        }
      } catch {
        if (mounted) {
          setMermaidScript(null);
        }
      }
    };
    loadMermaid();
    return () => {
      mounted = false;
    };
  }, []);

  return mermaidScript;
}
