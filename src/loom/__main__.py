"""CLI: run, resume, and attest LOOM simulations. argparse only, no deps."""

from __future__ import annotations

import argparse
import sys

from . import chrysalis
from .coherence import classify
from .engine import ShuttleEngine, SimConfig, SimResult


def _print_summary(result: SimResult) -> None:
    print("\n=== summary ===")
    print(f"ticks run          : {result.ticks_run}")
    print(f"max r              : {result.max_r:.4f}")
    print(f"collapse samples   : {int((result.r_trajectory >= 0.97).sum())} (must be 0)")
    print(f"final emergency    : {result.final_level.name}")
    print(f"halted             : {result.halted}" + (f" ({result.halted_reason})" if result.halted else ""))
    print(f"fragmented ticks   : {result.fragmented_ticks}")
    print(f"wall time          : {result.wall_time_s:.2f}s "
          f"({1e3 * result.wall_time_s / max(result.ticks_run, 1):.3f} ms/tick)")
    print("bands              :", ", ".join(f"{k}={v}" for k, v in sorted(result.band_counts.items())))
    print("actions            :")
    for key, count in sorted(result.action_counts.items()):
        print(f"  {key:45s} {count}")


def _run_engine(engine: ShuttleEngine, ticks: int | None, report_every: int) -> SimResult:
    if report_every > 0:
        total = engine.config.ticks if ticks is None else ticks
        remaining = total
        chunks: list[SimResult] = []
        import numpy as np

        while remaining > 0 and not engine.bus.halted:
            chunk = engine.run(min(report_every, remaining))
            chunks.append(chunk)
            remaining -= chunk.ticks_run
            band = classify(engine.last_r)
            print(
                f"tick {engine.tick_index:>7d}  r={engine.last_r:.4f}  band={band.name:<18s}"
                f"  level={engine.emergency.level.name:<4s}  K={engine.coupling:.3f}"
            )
            if chunk.ticks_run == 0:
                break
        # merge chunks into one result
        r = np.concatenate([c.r_trajectory for c in chunks]) if chunks else np.array([])
        last = chunks[-1] if chunks else None
        band_counts: dict[str, int] = {}
        for c in chunks:
            for k, v in c.band_counts.items():
                band_counts[k] = band_counts.get(k, 0) + v
        return SimResult(
            r_trajectory=r,
            max_r=float(r.max()) if len(r) else 0.0,
            ticks_run=int(sum(c.ticks_run for c in chunks)),
            final_level=engine.emergency.level,
            halted=engine.bus.halted,
            halted_reason=engine.bus.halt_reason,
            band_counts=band_counts,
            action_counts=last.action_counts if last else {},
            fragmented_ticks=sum(c.fragmented_ticks for c in chunks),
            wall_time_s=sum(c.wall_time_s for c in chunks),
        )
    return engine.run(ticks)


def cmd_run(args: argparse.Namespace) -> int:
    config = SimConfig(
        ticks=args.ticks,
        k_initial=args.k,
        k_ramp=args.ramp,
        noise_std=args.noise,
        seed=args.seed,
        prevention_enabled=not args.no_prevention,
        snapshot_path=args.out,
    )
    engine = ShuttleEngine(config)
    print(f"LOOM run: session={config.session_id} seed={config.seed} "
          f"prevention={'on' if config.prevention_enabled else 'OFF'}")
    result = _run_engine(engine, None, args.report_every)
    _print_summary(result)
    if args.out and not engine.bus.halted:
        engine.save_state(args.out)
        print(f"\nstate saved to {args.out}")
    attestation = engine.bus.attest()
    print(f"attestation        : records={attestation.record_count} "
          f"healthy={attestation.log_healthy} halted={attestation.halted}")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    state = chrysalis.load(args.state)
    engine, continuity = ShuttleEngine.reconstitute(state)
    print(f"reconstituted session={state.session_id} at tick {state.tick}")
    print(f"continuity: {continuity.note}")
    result = _run_engine(engine, args.ticks, args.report_every)
    _print_summary(result)
    if args.out and not engine.bus.halted:
        engine.save_state(args.out)
        print(f"\nstate saved to {args.out}")
    return 0


def cmd_attest(args: argparse.Namespace) -> int:
    try:
        state = chrysalis.load(args.state)
    except chrysalis.IntegrityError as exc:
        print(f"INTEGRITY FAILURE: {exc}")
        return 1
    print(f"snapshot OK: session={state.session_id} tick={state.tick} "
          f"schema=v{state.schema_version}")
    print(f"integrity sha256={state.integrity_hash()}")
    print(f"shadow record entries={len(state.shadow_record)} (append-only)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="loom", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run a simulation")
    p_run.add_argument("--ticks", type=int, default=5000)
    p_run.add_argument("--k", type=float, default=0.0, help="initial coupling")
    p_run.add_argument("--ramp", type=float, default=0.0, help="coupling drive per tick")
    p_run.add_argument("--noise", type=float, default=0.02)
    p_run.add_argument("--seed", type=int, default=0)
    p_run.add_argument("--no-prevention", action="store_true")
    p_run.add_argument("--out", type=str, default=None, help="save state here")
    p_run.add_argument("--report-every", type=int, default=500)
    p_run.set_defaults(func=cmd_run)

    p_resume = sub.add_parser("resume", help="reconstitute from a state file and continue")
    p_resume.add_argument("--state", type=str, required=True)
    p_resume.add_argument("--ticks", type=int, default=1000)
    p_resume.add_argument("--out", type=str, default=None)
    p_resume.add_argument("--report-every", type=int, default=500)
    p_resume.set_defaults(func=cmd_resume)

    p_attest = sub.add_parser("attest", help="verify a state file's integrity")
    p_attest.add_argument("--state", type=str, required=True)
    p_attest.set_defaults(func=cmd_attest)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
