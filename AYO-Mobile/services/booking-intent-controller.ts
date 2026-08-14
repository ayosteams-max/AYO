import { createBookingPreviewWireRequest,parseBookingPreview,parseBookingPreviewInput,parseGeneratedBookingIdentifiers,sameBookingPreviewInput,type BookingPreviewInput } from '../domain/booking-contracts.ts';
import { createDraftRecord,failPreview,lockPreview,stalePreview,viewOf,type BookingContinuity,type BookingIntentView,type BookingPreviewResult } from '../domain/booking-intent.ts';
import type { BookingApi } from './booking-api.ts';
import { InMemoryBookingIntentStore } from './booking-intent-store.ts';

export type BookingPreviewTransport=Pick<BookingApi,'preview'>; export type BookingIdentifierGenerator=()=>string; type ContinuityReader=()=>BookingContinuity|undefined;
type Flight=Readonly<{generation:number;input:BookingPreviewInput;scope:{invalidated?:BookingPreviewResult};abort:AbortController;promise:Promise<BookingPreviewResult>}>;
function secureIdentifier():string{if(!globalThis.crypto?.randomUUID) throw new Error('secure_booking_identity_unavailable');return globalThis.crypto.randomUUID();}
type SimpleOutcome='retired'|'cleared'|'superseded'|'conflicting_request'|'invalid_request'|'cancelled';
const result=(outcome:SimpleOutcome):Readonly<{outcome:SimpleOutcome}>=>Object.freeze({outcome});

export class BookingIntentController {
  private readonly store=new InMemoryBookingIntentStore(); private flight?:Flight; private generation=0; private continuity?:BookingContinuity; private terminal:'idle'|'retired'='idle';
  private readonly api:BookingPreviewTransport;private readonly readContinuity:ContinuityReader;private readonly generateId:BookingIdentifierGenerator;private readonly clock:()=>number;
  constructor(api:BookingPreviewTransport,readContinuity:ContinuityReader,generateId:BookingIdentifierGenerator=secureIdentifier,clock:()=>number=Date.now){this.api=api;this.readContinuity=readContinuity;this.generateId=generateId;this.clock=clock;}
  begin(value:unknown):BookingIntentView {
    if(this.store.read()) throw new Error('active_booking_intent_exists'); const continuity=this.readContinuity(); if(!continuity||!continuity.isCurrent()) throw new Error('booking_identity_unavailable');
    const input=parseBookingPreviewInput(value);let generated;try{generated=parseGeneratedBookingIdentifiers({intentId:this.generateId(),clientPreviewId:this.generateId(),bookingSession:this.generateId(),pickupId:this.generateId(),destinationId:this.generateId()});}catch{this.store.clear();throw new Error('invalid_booking_identifiers');}
    const request=createBookingPreviewWireRequest(input,generated); this.continuity=continuity;this.terminal='idle';this.store.replace(createDraftRecord({intentId:generated.intentId,clientPreviewId:generated.clientPreviewId,bookingSession:generated.bookingSession,continuity,input,request}));return this.read();
  }
  preview(value:unknown,signal?:AbortSignal):Promise<BookingPreviewResult>{
    let input:BookingPreviewInput;try{input=parseBookingPreviewInput(value);}catch{return Promise.resolve(result('invalid_request'));}
    if(this.flight)return sameBookingPreviewInput(this.flight.input,input)?this.flight.promise:Promise.resolve(result('conflicting_request'));
    const current=this.store.read();if(!current||current.status!=='draft'||!current.input||!current.request||!sameBookingPreviewInput(current.input,input))return Promise.resolve(result('conflicting_request'));const request=current.request;
    if(signal?.aborted){this.store.clear();this.terminal='retired';return Promise.resolve(result('cancelled'));}
    const generation=++this.generation,scope:{invalidated?:BookingPreviewResult}={},abort=new AbortController();const cancel=()=>{if(!scope.invalidated){scope.invalidated=result('cancelled');this.generation+=1;this.store.clear();this.terminal='retired';abort.abort();}};signal?.addEventListener('abort',cancel,{once:true});this.store.replace({...current,status:'previewing'});
    const operation=async():Promise<BookingPreviewResult>=>{try{if(scope.invalidated)return scope.invalidated;if(!this.current(generation,current.continuity))return result('superseded');const raw=await this.api.preview(request,abort.signal);const preview=parseBookingPreview(raw,this.clock());if(scope.invalidated)return scope.invalidated;if(!this.current(generation,current.continuity))return result('superseded');const active=this.store.read();if(!active||active.status!=='previewing')return result('superseded');if(this.clock()>=Date.parse(preview.expiresAt)){const stale=stalePreview(active);this.store.replace(stale);return Object.freeze({outcome:'stale',reason:'preview_expired',snapshot:viewOf(stale)});}const locked=lockPreview(active,preview);this.store.replace(locked);return Object.freeze({outcome:'confirmation_locked',snapshot:viewOf(locked)});}catch{if(scope.invalidated)return scope.invalidated;if(!this.current(generation,current.continuity))return result('superseded');const active=this.store.read();if(!active||active.status!=='previewing')return result('superseded');try{const failed=failPreview(active);this.store.replace(failed);return Object.freeze({outcome:'failed_safe',reason:'preview_unavailable',snapshot:viewOf(failed)});}catch{return result('superseded');}}};
    const promise=Promise.resolve().then(operation).catch(()=>result('superseded')).finally(()=>{try{signal?.removeEventListener('abort',cancel);}catch{}if(this.flight?.scope===scope)this.flight=undefined;});
    this.flight=Object.freeze({generation,input,scope,abort,promise});return promise;
  }
  read():BookingIntentView{const current=this.store.read();if(current&&!current.continuity.isCurrent()){this.invalidate('superseded');this.store.clear();this.terminal='retired';return Object.freeze({status:'retired'});}if(current?.status==='confirmation_locked'&&current.preview&&this.clock()>=Date.parse(current.preview.expiresAt)){const stale=stalePreview(current);this.store.replace(stale);return viewOf(stale);}return current?viewOf(current):Object.freeze({status:this.terminal});}
  replaceIdentity():BookingIntentView{const next=this.readContinuity();if(next===this.continuity&&next?.isCurrent())return this.read();this.invalidate('superseded');this.continuity=next;this.store.clear();this.terminal='retired';return this.read();}
  retire():BookingIntentView{this.invalidate('retired');this.store.clear();this.terminal='retired';return this.read();}
  clear():BookingIntentView{this.invalidate('cleared');this.store.clear();this.terminal='idle';return this.read();}
  private invalidate(outcome:'retired'|'cleared'|'superseded'){this.generation+=1;if(this.flight){this.flight.scope.invalidated=result(outcome);this.flight.abort.abort();this.flight=undefined;}}
  private current(generation:number,continuity:BookingContinuity){return generation===this.generation&&continuity===this.continuity&&continuity.isCurrent();}
}
