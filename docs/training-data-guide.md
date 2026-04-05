# Training Data Guide — Sock Sorting with Pi0.5 LoRA

## Policy: Pi0.5 (LoRA fine-tuning)

We are using Pi0.5 (3B param VLA from Physical Intelligence) fine-tuned via LoRA,
trained on the RTX Pro 4500 (32GB VRAM). Pi0.5 is pretrained on diverse manipulation
data, so it needs **far fewer episodes** than ACT (which needed 80-100).

**Current status:** 11 episodes recorded and training in progress. Evaluate the
model first, then record targeted episodes for specific failure cases.

## Why Socks Are Hard

Socks are uniquely challenging for manipulation:

- **Floppy and deformable** — flat spread, bunched, folded, crumpled
- **Low-profile** — thin fabric lying flat is hard to grasp from above
- **Stacking required** — sorting means placing one sock ON TOP of its match
- **Variable grip** — thin dress socks vs thick athletic socks behave differently

Pi0.5's pretrained manipulation knowledge handles much of the general dexterity,
but sock-specific scenarios may still need targeted training data.

## Skill Breakdown

### 1. Pick Flat Sock (30 episodes)

Sock is spread out flat on the mat. The most common starting state.

**Variation across episodes:**
- Pick from all reachable grid zones (near, far, left, right, center)
- Different sock sizes (ankle, crew, knee-high)
- Different fabrics (thin dress, thick athletic, fuzzy)
- Vary approach angle slightly (gripper orientation via wrist roll)
- Some episodes: grab sock by toe end; others by cuff; others by middle

**Key technique:** Come down slow, let the gripper jaws straddle the sock, close
firmly, pause 0.5s before lifting to let fabric bunch into the grip.

### 2. Pick Bunched/Folded Sock (20 episodes)

Sock is crumpled, loosely folded, or balled up. This happens after failed grasps
or when socks land in a pile.

**Variation:**
- Different degrees of bunching (loosely folded vs tightly balled)
- Different grid positions
- Approach from different angles — some bunched socks are easier from the side

**Key technique:** May need to approach from a slightly higher hover point since
the sock sits taller when bunched.

### 3. Place on Empty Mat (20 episodes)

Release a held sock onto an empty grid square. This is the easier placement.

**Variation:**
- Place at different grid positions across the workspace
- Release from different heights (hover vs near-table)
- Different sock weights in the gripper

**Key technique:** Open gripper smoothly — a jerky open can fling the sock.

### 4. Place on Top of Another Sock (25 episodes)

The critical sorting move: place a sock ON TOP of its match that's already on the mat.
This is harder because:
- The target is now ~1cm higher (sock thickness)
- You need to release accurately so both socks stay together
- Opening too fast can push the bottom sock away

**Variation:**
- Target sock flat vs bunched
- Different grid positions
- Different sock thicknesses (stacking two thin vs two thick)

**Key technique:** Come down to hover height, release gently. Don't try to push
down onto the sock — just drop from ~2cm above.

### 5. Failed Grasp Recovery (15 episodes)

Demonstrate what to do when a grasp fails — the gripper closes but the sock isn't
picked up, or the sock slips during lift.

**How to record these:**
1. Intentionally do a bad grasp (close gripper on edge of sock so it slips)
2. Lift — sock falls back
3. Re-approach and grasp again successfully
4. Complete the move

**Variation:**
- Fail on different sock types
- Fail at different positions
- Some episodes: sock partially grabbed then dropped during lift
- Recovery: slightly adjust approach angle or position before retry

## Episode Strategy with Pi0.5

Pi0.5's pretrained knowledge means you don't need to teach basic manipulation from
scratch. Instead, record episodes to teach your **specific workspace, sock types,
and task**.

### Phase 1: Basic Pick-and-Place (done — 11 episodes)
Flat socks, simple pick and place. This is what was recorded initially.

### Phase 2: Targeted Episodes (record after evaluating Phase 1 model)
Only record what the model fails at. Evaluate, identify failure modes, then record
5-10 targeted episodes per failure type:

| Skill | Episodes | When to record |
|-------|----------|----------------|
| Pick flat sock | 11 (done) | Phase 1 — already recorded |
| Pick bunched sock | 5-10 | If model fails on crumpled/folded socks |
| Place on top of sock | 5-10 | If stacking accuracy is poor |
| Failed grasp recovery | 5-10 | If model doesn't re-attempt after misses |
| **Total estimate** | **20-30** | **Evaluate between phases** |

This is dramatically fewer than the original 80-100 plan for ACT. The key insight:
**don't record episodes for skills the pretrained model already handles.**

## Recording Strategy (Pi0.5 LoRA)

### Evaluate-Then-Record Loop
1. Train on current episodes
2. Run inference on the arm, observe failure modes
3. Record 5-10 episodes targeting specific failures
4. Retrain (LoRA is fast on RTX Pro 4500)
5. Repeat until performance is acceptable

### If More Episodes Are Needed

**Stacking session (~5-10 episodes):**
- Pre-place a sock at the target position before each episode
- Pick a matching sock, place it on top
- Vary target sock state (flat vs slightly bunched)

**Bunched sock session (~5-10 episodes):**
- Crumple/fold socks before each episode
- Include intentional failed grasps with recovery

## Dataset Organization

Record everything into a single `sock_sorting` dataset. LeRobot handles
episode indexing. Pi0.5 learns from the full distribution — it doesn't
need separate skill labels.

```bash
# Record new episodes (resumes from last episode number)
./scripts/record.sh /dev/tty.FOLLOWER /dev/tty.LEADER sock_sorting --resume
```

## What NOT to Train

- **Sock identification** — Claude Vision handles this, not the arm policy
- **Path planning between grid squares** — the coordinator + calibration table handles this
- **Sorting order** — Claude decides which sock to pick next

The Pi0.5 policy only needs to master the physical manipulation:
approach, grasp, lift, carry, place, release.

## Tips for Better Training Data

1. **Watch through camera feeds** — the model sees what the camera sees, not what you see
2. **Smooth, deliberate movements** — jerky motions confuse the policy
3. **Consistent speed** — don't rush. 20-30 seconds per episode is ideal
4. **Reset between episodes** — place the sock fresh each time
5. **Vary lighting slightly** across sessions (not within a session) to build robustness
6. **Leave grid labels visible** — the model may use them for spatial reference
7. **Don't cheat the camera** — if you can't see the sock in the camera feed, the model can't either
