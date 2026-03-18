# Recording Checklist

Pre-recording checklist for SO-101 pick-and-place training episodes.

## Before You Start (One-Time Setup)

- [ ] Arms assembled, motors set up, calibration complete
- [ ] Both cameras plugged **directly into USB ports** (no hubs)
- [ ] Run `lerobot-find-cameras` — note the index for each camera
- [ ] Update `backend/.env` with camera indices and arm ports
- [ ] Cameras rigidly mounted (clamp, bracket, tape — no wobbly tripods)
- [ ] Top-down camera: directly above workspace, pointing straight down
- [ ] Front/side camera: eye-level, angled toward workspace
- [ ] Grid mat laid flat on workspace, coordinates visible to top camera
- [ ] Verify camera views: `scripts/find_cameras.sh` — check both feeds

## Before Each Recording Session

- [ ] Workspace is clean — **nothing but grid mat + sock in frame**
- [ ] No clutter visible to either camera
- [ ] Consistent lighting — no moving shadows, no windows with changing sunlight
- [ ] Leader and follower arms powered on
- [ ] Run `scripts/teleoperate.sh` briefly to confirm both arms respond
- [ ] Cameras confirmed working (check live feeds)

## During Recording

- [ ] Watch through the **camera feeds**, not directly at the follower arm
- [ ] One sock on the mat at a time (for pick-and-place skill training)
- [ ] Each episode: home -> approach -> grasp -> lift -> move -> release -> home
- [ ] **Vary every episode:**
  - Pick from different grid positions (spread across the whole mat)
  - Place at different target locations
  - Different sock colors and sizes
  - Different approach angles
  - Slightly different gripper heights
- [ ] Move at a smooth, moderate pace — no jerky movements
- [ ] If you mess up an episode, it's fine — discard and redo
- [ ] Target: **50 episodes minimum** (~25-30 min of teleoperation)

## After Recording

- [ ] Verify dataset was saved: check `~/.cache/huggingface/lerobot/sock_sorting/`
- [ ] Replay a few episodes to sanity check quality
- [ ] Sync dataset to Jetson: `scripts/sync_dataset_to_jetson.sh`
- [ ] **Do NOT move the cameras** — positions must stay identical for evaluation

## Recording Command

```bash
./scripts/record.sh /dev/tty.FOLLOWER_PORT /dev/tty.LEADER_PORT sock_sorting
```

## Resume If Interrupted

If recording is interrupted, re-run the same command with `--control.resume=true` appended.
