import {createContext,type PropsWithChildren,useCallback,useContext,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {useIdentityContinuity,useIdentitySession} from '@/contexts/identity-session';
import type {BookingPreviewInput} from '@/domain/booking-contracts';
import type {BookingIntentView,BookingPreviewResult} from '@/domain/booking-intent';
import {BookingIntentController,type BookingIdentifierGenerator,type BookingPreviewTransport} from '@/services/booking-intent-controller';

export type BookingIntentPresentation=Readonly<{status:BookingIntentView['status'];busy:boolean;disabled:boolean;stale:boolean;success:false;safeReason?:string}>;
export type BookingIntentRead=Readonly<{state:BookingIntentPresentation;begin(input:BookingPreviewInput):BookingIntentPresentation;requestPreview(input:BookingPreviewInput,signal?:AbortSignal):Promise<BookingPreviewResult>;retire():void;clear():void}>;
const Context=createContext<BookingIntentRead|undefined>(undefined);
function presentation(view:BookingIntentView):BookingIntentPresentation{return Object.freeze({status:view.status,busy:view.status==='previewing',disabled:view.status!=='draft',stale:view.status==='stale'||view.status==='retired',success:false,...(view.safeReason?{safeReason:view.safeReason}:{})});}
type BookingIntentProviderProps=PropsWithChildren<Readonly<{previewTransport:BookingPreviewTransport;identifierGenerator?:BookingIdentifierGenerator;clock?:()=>number}>>;
export function BookingIntentProvider({children,previewTransport,identifierGenerator,clock}:BookingIntentProviderProps){
  useIdentitySession();const continuityReader=useIdentityContinuity();const continuity=continuityReader.readIdentityContinuity();const continuityRef=useRef(continuity);continuityRef.current=continuity;const controller=useMemo(()=>new BookingIntentController(previewTransport,()=>continuityRef.current,identifierGenerator,clock),[clock,identifierGenerator,previewTransport]);const [,render]=useState(0);const generation=useRef(0),previous=useRef(continuity),mounted=useRef(true);
  useLayoutEffect(()=>{mounted.current=true;return()=>{mounted.current=false;generation.current+=1;controller.retire();};},[controller]);
  useLayoutEffect(()=>{if(previous.current!==continuity){previous.current=continuity;generation.current+=1;controller.replaceIdentity();render(value=>value+1);}},[continuity,controller]);
  const begin=useCallback((input:BookingPreviewInput)=>{const next=presentation(controller.begin(input));render(value=>value+1);return next;},[controller]);
  const requestPreview=useCallback(async(input:BookingPreviewInput,signal?:AbortSignal)=>{const current=++generation.current;render(value=>value+1);const outcome=await controller.preview(input,signal);if(mounted.current&&current===generation.current&&continuity?.isCurrent())render(value=>value+1);return outcome;},[continuity,controller]);
  const retire=useCallback(()=>{generation.current+=1;controller.retire();render(value=>value+1);},[controller]);const clear=useCallback(()=>{generation.current+=1;controller.clear();render(value=>value+1);},[controller]);
  const value=useMemo<BookingIntentRead>(()=>Object.freeze({get state(){return presentation(controller.read());},begin,requestPreview,retire,clear}),[begin,clear,controller,requestPreview,retire]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export function useBookingIntent(){const value=useContext(Context);if(!value)throw new Error('booking_intent_provider_required');return value;}
