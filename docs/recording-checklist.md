# Recording Checklist

Pre-recording checklist for SO-101 pick-and-place training episodes.

## Before You Start (One-Time Setup)

- [ ] Arms assembled, motors set up, calibration complete
- [ ] All 3 cameras plugged **directly into USB ports** (no hubs)
- [ ] Run `lerobot-find-cameras` — note the index for each camera
- [ ] Update `backend/.env` with camera indices (`CAMERA_RIGHT_INDEX`, `CAMERA_WRIST_INDEX`, `CAMERA_ACROSS_INDEX`) and arm ports
- [ ] Right camera: ~20" high, to the right of arm, looking down — rigidly mounted
- [ ] Wrist camera: mounted on gripper, cable has slack and won't snag during moves
- [ ] Across camera: opposite side of arm, looking down at workspace — rigidly mounted
- [ ] Grid mat laid flat on workspace, coordinates visible to right + across cameras
- [ ] Verify all 3 camera views: `lerobot-find-cameras` — check all feeds

## Before Each Recording Session

- [ ] Workspace is clean — **nothing but grid mat + sock in frame**
- [ ] No clutter visible to any camera
- [ ] Consistent lighting — no moving shadows, no windows with changing sunlight
- [ ] Leader and follower arms powered on
- [ ] Run `scripts/teleoperate.sh` briefly to confirm both arms respond
- [ ] Cameras confirmed working (check live feeds)

## During Recording

- [ ] Watch through the **camera feeds**, not directly at the follower arm
- [ ] Each episode: home -> approach -> grasp -> lift -> move -> release -> home
- [ ] Move at a smooth, moderate pace — no jerky movements
- [ ] If you mess up an episode, it's fine — discard and redo
- [ ] Target: **80-100 episodes** across 3 sessions (~60 min total teleoperation)

### Session 1: Basic Pick-and-Place (40 episodes)
- [ ] One flat sock on mat at a time
- [ ] Pick from every reachable grid zone (near, far, left, right)
- [ ] Place on empty mat squares
- [ ] Mix 4-5 different sock types (thin, thick, different sizes)
- [ ] Vary approach angle and gripper height

### Session 2: Stacking Pairs (25 episodes)
- [ ] Pre-place a "target" sock at the destination before each episode
- [ ] Pick a matching sock and place it **on top** of the target
- [ ] Vary target sock state (flat vs slightly bunched)
- [ ] Different grid positions for the pair

### Session 3: Bunched Socks + Recovery (35 episodes)
- [ ] Crumple/fold socks into different shapes before each episode
- [ ] Include **intentional failed grasps** with re-approach and recovery
- [ ] Mix in some normal flat picks for variety

See `docs/training-data-guide.md` for full details on each skill type.

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
