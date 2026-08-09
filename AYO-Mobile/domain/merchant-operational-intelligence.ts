export type MerchantAcknowledgementPresentationStatus =
  | 'idle'
  | 'submitting'
  | 'reconciling'
  | 'applied'
  | 'outcome_unknown'
  | 'retry_same_attempt'
  | 'rejected'
  | 'invalidated';

export type MerchantOperationalIntelligenceInput = Readonly<{
  acknowledgementStatus: MerchantAcknowledgementPresentationStatus;
  canAcknowledgeArrival: boolean;
  canReconcileAcknowledgeArrival: boolean;
}>;

export type MerchantOperationalIntelligenceResult =
  | Readonly<{ recommendation: 'no_action'; reason: 'NO_CURRENT_ACK_ACTION' | 'ACK_AUTHORITY_CHANGED' | 'UNSUPPORTED_ACK_STATE'; userActionAvailable: false }>
  | Readonly<{ recommendation: 'acknowledge_arrival'; reason: 'ACK_ALLOWED_BY_CAPABILITY'; userActionAvailable: true }>
  | Readonly<{ recommendation: 'acknowledging_arrival'; reason: 'ACK_IN_PROGRESS'; userActionAvailable: false }>
  | Readonly<{ recommendation: 'arrival_acknowledged'; reason: 'ACK_CONFIRMED'; userActionAvailable: false }>
  | Readonly<{ recommendation: 'check_acknowledgement_status'; reason: 'ACK_RESULT_UNCERTAIN_RECONCILIATION_AVAILABLE'; userActionAvailable: true }>
  | Readonly<{ recommendation: 'checking_acknowledgement_status'; reason: 'ACK_RECONCILIATION_IN_PROGRESS'; userActionAvailable: false }>
  | Readonly<{ recommendation: 'retry_same_acknowledgement'; reason: 'ACK_SAME_ATTEMPT_RETRY_AVAILABLE'; userActionAvailable: true }>
  | Readonly<{ recommendation: 'retry_acknowledgement'; reason: 'ACK_RETRY_ALLOWED_BY_CAPABILITY'; userActionAvailable: true }>
  | Readonly<{
    recommendation: 'acknowledgement_issue';
    reason: 'ACK_RESULT_UNCERTAIN_NO_CURRENT_ACTION' | 'ACK_SAME_ATTEMPT_RETRY_NOT_CURRENTLY_ALLOWED' | 'ACK_REJECTED_NO_CURRENT_ACTION';
    userActionAvailable: false;
  }>;

const result = <const T extends MerchantOperationalIntelligenceResult>(value: T): T => Object.freeze(value);

const results = Object.freeze({
  noAction: result({ recommendation: 'no_action', reason: 'NO_CURRENT_ACK_ACTION', userActionAvailable: false }),
  authorityChanged: result({ recommendation: 'no_action', reason: 'ACK_AUTHORITY_CHANGED', userActionAvailable: false }),
  unsupported: result({ recommendation: 'no_action', reason: 'UNSUPPORTED_ACK_STATE', userActionAvailable: false }),
  acknowledge: result({ recommendation: 'acknowledge_arrival', reason: 'ACK_ALLOWED_BY_CAPABILITY', userActionAvailable: true }),
  acknowledging: result({ recommendation: 'acknowledging_arrival', reason: 'ACK_IN_PROGRESS', userActionAvailable: false }),
  acknowledged: result({ recommendation: 'arrival_acknowledged', reason: 'ACK_CONFIRMED', userActionAvailable: false }),
  checkStatus: result({ recommendation: 'check_acknowledgement_status', reason: 'ACK_RESULT_UNCERTAIN_RECONCILIATION_AVAILABLE', userActionAvailable: true }),
  checkingStatus: result({ recommendation: 'checking_acknowledgement_status', reason: 'ACK_RECONCILIATION_IN_PROGRESS', userActionAvailable: false }),
  retrySame: result({ recommendation: 'retry_same_acknowledgement', reason: 'ACK_SAME_ATTEMPT_RETRY_AVAILABLE', userActionAvailable: true }),
  retry: result({ recommendation: 'retry_acknowledgement', reason: 'ACK_RETRY_ALLOWED_BY_CAPABILITY', userActionAvailable: true }),
  uncertain: result({ recommendation: 'acknowledgement_issue', reason: 'ACK_RESULT_UNCERTAIN_NO_CURRENT_ACTION', userActionAvailable: false }),
  retryUnavailable: result({ recommendation: 'acknowledgement_issue', reason: 'ACK_SAME_ATTEMPT_RETRY_NOT_CURRENTLY_ALLOWED', userActionAvailable: false }),
  rejected: result({ recommendation: 'acknowledgement_issue', reason: 'ACK_REJECTED_NO_CURRENT_ACTION', userActionAvailable: false }),
});

/** Deterministically interprets presentation-safe ACK evidence without command access. */
export function recommendMerchantOperationalAction(
  input: MerchantOperationalIntelligenceInput,
): MerchantOperationalIntelligenceResult {
  if (typeof input?.canAcknowledgeArrival !== 'boolean' || typeof input?.canReconcileAcknowledgeArrival !== 'boolean') return results.unsupported;
  if (input.canReconcileAcknowledgeArrival && input.acknowledgementStatus !== 'outcome_unknown') return results.unsupported;
  if (input.canAcknowledgeArrival && ['submitting', 'reconciling', 'applied', 'outcome_unknown', 'invalidated'].includes(input.acknowledgementStatus)) return results.unsupported;
  switch (input.acknowledgementStatus) {
    case 'idle': return input.canAcknowledgeArrival ? results.acknowledge : results.noAction;
    case 'submitting': return results.acknowledging;
    case 'applied': return results.acknowledged;
    case 'outcome_unknown': return input.canReconcileAcknowledgeArrival ? results.checkStatus : results.uncertain;
    case 'reconciling': return results.checkingStatus;
    case 'retry_same_attempt': return input.canAcknowledgeArrival ? results.retrySame : results.retryUnavailable;
    case 'rejected': return input.canAcknowledgeArrival ? results.retry : results.rejected;
    case 'invalidated': return results.authorityChanged;
    default: return results.unsupported;
  }
}
