import { createContext, type PropsWithChildren, useContext, useMemo, useState } from 'react';

import type { SupportedLocale } from '@/localization/authentication';

type LanguageContextValue = Readonly<{ locale: SupportedLocale; setLocale: (locale: SupportedLocale) => void }>;
const LanguageContext = createContext<LanguageContextValue | undefined>(undefined);

export function LanguageProvider({ children }: PropsWithChildren) {
  const [locale, setLocale] = useState<SupportedLocale>('en');
  const value = useMemo(() => ({ locale, setLocale }), [locale]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const value = useContext(LanguageContext);
  if (!value) throw new Error('language_provider_required');
  return value;
}
