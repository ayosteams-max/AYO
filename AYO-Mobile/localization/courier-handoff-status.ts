import type { SupportedLocale } from './authentication';
import type { HandoffStatusCategory } from '@/domain/courier-handoff-status';

const english = {
  title: 'Handoff status', preProduction: 'PRE-PRODUCTION', loading: 'Checking current handoff status…',
  stale: 'Information may be out of date', unavailable: 'Unable to confirm current status', malformed: 'AYO could not safely read this status.', conflicting: 'Current handoff information does not agree.',
  refresh: 'Refresh', refreshing: 'Refreshing…', account: 'Account', returnAreas: 'Return to operating areas',
  startTravel: 'Start travel to merchant', startingTravel: 'Starting travel…', startConfirmed: 'Travel start confirmed', startConfirmedHelp: 'Refresh to see the latest current status.',
  outcomeUnknown: 'AYO could not confirm whether travel started.', outcomeUnknownHelp: 'Do not start again until you check the current status.', checkStatus: 'Check current status', checkingStatus: 'Checking current status…',
  retryReady: 'AYO confirmed that you may send the same start request again.', retryStartTravel: 'Send start request again', refreshRequired: 'Refresh current information before trying another action.',
  currentWorkChanged: 'This action is no longer available. Refresh your current work.', genericCommandFailure: 'AYO could not safely confirm this action. Refresh current information.',
  markArrived: 'Mark arrived', markingArrival: 'Sending arrival declaration…', arrivalConfirmed: 'Arrival declaration confirmed', arrivalConfirmedHelp: 'AYO confirmed the arrival declaration. Refresh to see the latest current status.',
  arrivalOutcomeUnknown: 'AYO could not confirm whether the arrival declaration was applied.', arrivalOutcomeUnknownHelp: 'Do not send it again until you check the current status.', arrivalRetryReady: 'AYO confirmed that you may send the same arrival request again.', retryMarkArrived: 'Send arrival request again',
  pickup_current: 'Pickup work is current', travelling: 'Travelling to the merchant', at_merchant: 'At the merchant', waiting_for_merchant: 'Waiting for merchant', ready_for_handoff: 'Ready for handoff', handoff_in_progress: 'Handoff in progress', pickup_confirmed: 'Pickup confirmed', pickup_ended: 'This pickup is no longer current',
  guidance_refresh: 'Refresh to confirm the latest status.', guidance_wait: 'Wait for the merchant to prepare the handoff.', guidance_ready: 'The handoff is ready. Follow the approved in-person process.', guidance_progress: 'The handoff is being confirmed.', guidance_confirmed: 'The handoff has been confirmed.', guidance_ended: 'Return to your operating areas for current work.',
} as const;
type Strings = { readonly [K in keyof typeof english]: string };
export type CourierHandoffCopy = Strings;
const amharic: Strings = {
  title: 'የርክክብ ሁኔታ', preProduction: 'ቅድመ-ምርት', loading: 'የአሁኑ የርክክብ ሁኔታ እየተረጋገጠ ነው…',
  stale: 'መረጃው ያረጀ ሊሆን ይችላል', unavailable: 'የአሁኑን ሁኔታ ማረጋገጥ አልተቻለም', malformed: 'AYO ይህን ሁኔታ በደህና ማንበብ አልቻለም።', conflicting: 'የአሁኑ የርክክብ መረጃ አይጣጣምም።',
  refresh: 'አድስ', refreshing: 'እየታደሰ ነው…', account: 'መለያ', returnAreas: 'ወደ የስራ ክፍሎች ተመለስ',
  startTravel: 'ወደ ነጋዴው መጓዝ ጀምር', startingTravel: 'የጉዞ መጀመር እየተላከ ነው…', startConfirmed: 'ጉዞው መጀመሩ ተረጋግጧል', startConfirmedHelp: 'የአሁኑን ሁኔታ ለማየት ያድሱ።',
  outcomeUnknown: 'ጉዞው መጀመሩን ማረጋገጥ አልቻልንም።', outcomeUnknownHelp: 'እንደገና ከመጀመርዎ በፊት የአሁኑን ሁኔታ ያረጋግጡ።', checkStatus: 'የአሁኑን ሁኔታ አረጋግጥ', checkingStatus: 'የአሁኑ ሁኔታ እየተረጋገጠ ነው…',
  retryReady: 'ተመሳሳዩን የመጀመር ጥያቄ እንደገና መላክ ይችላሉ።', retryStartTravel: 'የመጀመር ጥያቄውን እንደገና ላክ', refreshRequired: 'ሌላ እርምጃ ከመውሰድዎ በፊት የአሁኑን መረጃ ያድሱ።',
  currentWorkChanged: 'ይህ እርምጃ አሁን አይገኝም። የአሁኑን ሥራ ያድሱ።', genericCommandFailure: 'AYO ይህን እርምጃ በደህና ማረጋገጥ አልቻለም። የአሁኑን መረጃ ያድሱ።',
  markArrived: 'ነጋዴው ቦታ መድረሴን አሳውቅ', markingArrival: 'የመድረስ ማሳወቂያው እየተላከ ነው…', arrivalConfirmed: 'የመድረስ ማሳወቂያው ተረጋግጧል', arrivalConfirmedHelp: 'AYO የመድረስ ማሳወቂያውን አረጋግጧል። የቅርብ ጊዜውን ሁኔታ ለማየት ያድሱ።',
  arrivalOutcomeUnknown: 'AYO የመድረስ ማሳወቂያው መፈጸሙን ማረጋገጥ አልቻለም።', arrivalOutcomeUnknownHelp: 'የአሁኑን ሁኔታ እስኪያረጋግጡ ድረስ እንደገና አይላኩ።', arrivalRetryReady: 'ተመሳሳዩን የመድረስ ጥያቄ እንደገና መላክ እንደሚችሉ AYO አረጋግጧል።', retryMarkArrived: 'የመድረስ ጥያቄውን እንደገና ላክ',
  pickup_current: 'የማንሳት ስራው አሁንም የአሁኑ ነው', travelling: 'ወደ ነጋዴው በመጓዝ ላይ', at_merchant: 'ነጋዴው ቦታ ደርሷል', waiting_for_merchant: 'ነጋዴውን በመጠበቅ ላይ', ready_for_handoff: 'ለርክክብ ዝግጁ ነው', handoff_in_progress: 'ርክክቡ በሂደት ላይ ነው', pickup_confirmed: 'ማንሳቱ ተረጋግጧል', pickup_ended: 'ይህ የማንሳት ስራ ከእንግዲህ የአሁኑ አይደለም',
  guidance_refresh: 'የቅርብ ጊዜውን ሁኔታ ለማረጋገጥ ያድሱ።', guidance_wait: 'ነጋዴው ርክክቡን እስኪያዘጋጅ ይጠብቁ።', guidance_ready: 'ርክክቡ ዝግጁ ነው። የተፈቀደውን የአካል ርክክብ ሂደት ይከተሉ።', guidance_progress: 'ርክክቡ እየተረጋገጠ ነው።', guidance_confirmed: 'ርክክቡ ተረጋግጧል።', guidance_ended: 'የአሁኑን ስራ ለማየት ወደ የስራ ክፍሎችዎ ይመለሱ።',
};
export const courierHandoffCopy: Readonly<Record<SupportedLocale, Strings>> = { en: english, am: amharic };
export function guidanceKey(status: HandoffStatusCategory): keyof Strings {
  if (status === 'waiting_for_merchant') return 'guidance_wait';
  if (status === 'ready_for_handoff') return 'guidance_ready';
  if (status === 'handoff_in_progress') return 'guidance_progress';
  if (status === 'pickup_confirmed') return 'guidance_confirmed';
  if (status === 'pickup_ended') return 'guidance_ended';
  return 'guidance_refresh';
}
