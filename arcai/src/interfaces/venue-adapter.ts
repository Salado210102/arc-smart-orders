import type { Address } from "../types/branded.ts";
import type { TokenAmount } from "../types/money.ts";
import type { RoutePlan, VenueKind } from "../types/venue.ts";

export interface SimulationResult {
  readonly ok: boolean;
  readonly revertReason: string | null;
  readonly gasEstimate: bigint | null;
}

export interface VenueAdapter {
  readonly kind: VenueKind;
  readonly router: Address;
  quote(amountIn: TokenAmount, tokenOut: Address): Promise<RoutePlan>;
  simulate(plan: RoutePlan, sender: Address): Promise<SimulationResult>;
}
