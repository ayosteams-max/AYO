import type { BookingPreview, BookingPreviewInput, BookingPreviewWireRequest } from './booking-contracts.ts';

export type BookingIntentStatus='draft'|'previewing'|'confirmation_locked'|'failed_safe'|'stale';
export type BookingSafeReason='approved_consent_presentation_required'|'preview_unavailable'|'preview_expired';
export type BookingContinuity=Readonly<{isCurrent():boolean}>;
export type BookingIntentRecord=Readonly<{status:BookingIntentStatus;intentId:string;clientPreviewId:string;bookingSession:string;continuity:BookingContinuity;input?:BookingPreviewInput;request?:BookingPreviewWireRequest;preview?:BookingPreview;safeReason?:BookingSafeReason}>;
export type BookingIntentView=Readonly<{status:BookingIntentStatus|'idle'|'retired';safeReason?:BookingSafeReason}>;
export type BookingPreviewResult=
  |Readonly<{outcome:'confirmation_locked';snapshot:BookingIntentView}>
  |Readonly<{outcome:'failed_safe'|'stale';reason:BookingSafeReason;snapshot:BookingIntentView}>
  |Readonly<{outcome:'retired'|'cleared'|'superseded'|'conflicting_request'|'invalid_request'|'cancelled'}>;

export function createDraftRecord(values:Omit<BookingIntentRecord,'status'> & {input:BookingPreviewInput;request:BookingPreviewWireRequest}):BookingIntentRecord{return Object.freeze({...values,status:'draft'});}
export function lockPreview(intent:BookingIntentRecord,preview:BookingPreview):BookingIntentRecord{if(intent.status!=='previewing') throw new Error('illegal_booking_intent_transition');return Object.freeze({status:'confirmation_locked',intentId:intent.intentId,clientPreviewId:intent.clientPreviewId,bookingSession:intent.bookingSession,continuity:intent.continuity,preview,safeReason:'approved_consent_presentation_required'});}
export function failPreview(intent:BookingIntentRecord):BookingIntentRecord{if(intent.status!=='previewing') throw new Error('illegal_booking_intent_transition');return Object.freeze({status:'failed_safe',intentId:intent.intentId,clientPreviewId:intent.clientPreviewId,bookingSession:intent.bookingSession,continuity:intent.continuity,safeReason:'preview_unavailable'});}
export function stalePreview(intent:BookingIntentRecord):BookingIntentRecord{if(intent.status!=='previewing'&&intent.status!=='confirmation_locked') throw new Error('illegal_booking_intent_transition');return Object.freeze({status:'stale',intentId:intent.intentId,clientPreviewId:intent.clientPreviewId,bookingSession:intent.bookingSession,continuity:intent.continuity,safeReason:'preview_expired'});}
export function viewOf(intent?:BookingIntentRecord):BookingIntentView{return intent?Object.freeze({status:intent.status,...(intent.safeReason?{safeReason:intent.safeReason}:{})}):Object.freeze({status:'idle'});}
