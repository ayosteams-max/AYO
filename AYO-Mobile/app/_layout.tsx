import { DarkTheme, DefaultTheme, ThemeProvider } from '@react-navigation/native';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import 'react-native-reanimated';

import { useColorScheme } from '@/hooks/use-color-scheme';
import { IdentitySessionProvider } from '@/contexts/identity-session';
import { LanguageProvider } from '@/contexts/language';
import { OperationalContextProvider } from '@/contexts/operational-context';

export const unstable_settings = {
  anchor: '(tabs)',
};

export default function RootLayout() {
  const colorScheme = useColorScheme();

  return (
    <LanguageProvider><IdentitySessionProvider><OperationalContextProvider><ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
      <Stack>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="destination-search" options={{ headerShown: false, animation: 'slide_from_right' }} />
        <Stack.Screen name="auth" options={{ headerShown: false, animation: 'slide_from_bottom' }} />
        <Stack.Screen name="modal" options={{ presentation: 'modal', title: 'Modal' }} />
      </Stack>
      <StatusBar style="auto" />
    </ThemeProvider></OperationalContextProvider></IdentitySessionProvider></LanguageProvider>
  );
}
