# Training Data Guide — Expanded Skills for Sock Sorting

The original plan called for 50 episodes of a single "pick-and-place" skill. That's
a reasonable start for rigid objects, but socks are uniquely challenging:

- **Floppy and deformable** — flat spread, bunched, folded, crumpled
- **Low-profile** — thin fabric lying flat is hard to grasp from above
- **Stacking required** — sorting means placing one sock ON TOP of its match
- **Variable grip** — thin dress socks vs thick athletic socks behave differently

This guide defines the expanded set of training episodes needed for reliable sorting.

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

## Episode Count Summary

| Skill | Episodes | Time Est. |
|-------|----------|-----------|
| Pick flat sock | 30 | ~15 min |
| Pick bunched sock | 20 | ~10 min |
| Place on empty mat | 20 | ~10 min |
| Place on top of sock | 25 | ~15 min |
| Failed grasp recovery | 15 | ~10 min |
| **Total** | **110** | **~60 min** |

Note: Pick and place naturally pair up in a single episode (you pick, then place).
So "30 pick-flat + 20 place-empty" can overlap — a single episode records both
the pick AND the place. The counts above reflect emphasis: ensure at least that
many episodes feature each skill as the focus.

**Practical episode count: 80-100 episodes** with mixed pick/place combinations,
ensuring each skill gets adequate representation.

## Recording Strategy

### Session 1: Basic Pick-and-Place (40 episodes, ~30 min)
- Flat socks only, place on empty mat
- Focus on grid coverage — pick from every reachable zone
- Mix sock types (have 4-5 different pairs on hand)

### Session 2: Stacking (25 episodes, ~20 min)
- Pre-place a sock at the target position before each episode
- Pick a matching sock, place it on top
- Vary target sock state (flat vs slightly bunched)

### Session 3: Bunched + Recovery (35 episodes, ~25 min)
- Crumple/fold socks before each episode
- Include intentional failed grasps with recovery
- Mix in some normal flat picks too for variety

## Dataset Organization

Record everything into a single `sock_sorting` dataset. LeRobot handles
episode indexing. The ACT policy learns from the full distribution — it doesn't
need separate skill labels.

```bash
# Session 1
./scripts/record.sh /dev/tty.FOLLOWER /dev/tty.LEADER sock_sorting

# Sessions 2-3: resume from where you left off
./scripts/record.sh /dev/tty.FOLLOWER /dev/tty.LEADER sock_sorting
# Add --control.resume=true if interrupted
```

## What NOT to Train

- **Sock identification** — Claude Vision handles this, not the arm policy
- **Path planning between grid squares** — the coordinator + calibration table handles this
- **Sorting order** — Claude decides which sock to pick next

The ACT policy only needs to master the physical manipulation:
approach, grasp, lift, carry, place, release.

## Tips for Better Training Data

1. **Watch through camera feeds** — the model sees what the camera sees, not what you see
2. **Smooth, deliberate movements** — jerky motions confuse the policy
3. **Consistent speed** — don't rush. 20-30 seconds per episode is ideal
4. **Reset between episodes** — place the sock fresh each time
5. **Vary lighting slightly** across sessions (not within a session) to build robustness
6. **Leave grid labels visible** — the model may use them for spatial reference
7. **Don't cheat the camera** — if you can't see the sock in the camera feed, the model can't either
