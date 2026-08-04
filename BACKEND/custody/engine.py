from BACKEND.custody.models import CustodyAction, CustodyState


class CustodyConflict(ValueError):
    pass


def target_state(state: CustodyState, action: CustodyAction) -> CustodyState:
    transitions = {
        (CustodyState.WAITING, CustodyAction.SEAL): CustodyState.SEALED,
        (CustodyState.SEALED, CustodyAction.VERIFY): CustodyState.VERIFIED,
        (CustodyState.VERIFIED, CustodyAction.RELEASE): CustodyState.RELEASED,
        (CustodyState.RELEASED, CustodyAction.ACCEPT): CustodyState.ACCEPTED,
    }
    try:
        return transitions[(state, action)]
    except KeyError as error:
        raise CustodyConflict("invalid_custody_transition") from error
