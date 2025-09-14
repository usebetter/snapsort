from snapsort.cli import main

if __name__ == "__main__":
    # Ensure frozen-executable child processes (spawned by multiprocessing or
    # libraries that use it) don't re-run the CLI argument parser.
    try:
        import multiprocessing as _mp
        _mp.freeze_support()
    except Exception:
        pass
    raise SystemExit(main())
