# Listing 11.3 -- rollout.py: a rolling deployment, simulated.
# The orchestrator replaces instances a few at a time, and READINESS is the
# gate: a new instance receives traffic only after it reports ready, and the
# rollout advances only while new instances stay healthy. If new instances
# fail their readiness checks, the rollout HALTS and rolls back -- the fleet
# never ends up all-broken. This is Chapter 6's expand-contract made
# operational: old and new run together, and the deploy is reversible at
# every step.
import time

class Instance:
    def __init__(self, version, healthy=True):
        self.version = version
        self.healthy = healthy       # does it pass readiness once started?
        self.ready = False
    def start(self):
        # startup takes a moment; then readiness reflects health
        self.ready = self.healthy
        return self.ready

def rolling_deploy(fleet_size, new_version, batch, new_is_healthy):
    """Replace an all-old fleet with new_version, `batch` at a time."""
    fleet = [Instance("v1") for _ in range(fleet_size)]
    for i in fleet:
        i.start()
    print(f"start: {fleet_size} x v1, all ready")

    replaced = 0
    while replaced < fleet_size:
        n = min(batch, fleet_size - replaced)
        print(f"\nbatch: replacing {n} instance(s) with {new_version}")
        # bring up the new batch
        new_batch = [Instance(new_version, healthy=new_is_healthy)
                     for _ in range(n)]
        for inst in new_batch:
            inst.start()

        # THE GATE: do the new instances report ready?
        if not all(inst.ready for inst in new_batch):
            print(f"  new instances FAILED readiness -> HALT and roll back")
            print(f"  fleet stays at {fleet_size - replaced} x v1 serving "
                  f"traffic (old version never torn down until new proven)")
            return "rolled_back"

        # new batch healthy: now safe to retire an equal number of old
        for _ in range(n):
            fleet.pop()          # drain + terminate an old instance
        fleet.extend(new_batch)
        replaced += n
        serving = (f"{replaced} x {new_version} + "
                   f"{fleet_size - replaced} x v1")
        print(f"  new batch ready -> retired {n} old. Now serving: {serving}")
        print(f"  (both versions live -- the expand-contract window)")

    print(f"\ndone: {fleet_size} x {new_version}, zero downtime")
    return "deployed"

if __name__ == "__main__":
    print("=" * 60)
    print("SCENARIO A: healthy new version -- rollout completes")
    print("=" * 60)
    rolling_deploy(fleet_size=6, new_version="v2", batch=2, new_is_healthy=True)

    print("\n" + "=" * 60)
    print("SCENARIO B: broken new version -- rollout halts, fleet safe")
    print("=" * 60)
    rolling_deploy(fleet_size=6, new_version="v2-broken", batch=2,
                   new_is_healthy=False)
