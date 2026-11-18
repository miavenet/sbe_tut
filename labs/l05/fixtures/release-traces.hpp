// [claim: WP4-RELEASE]
// Declared events, not a network/consensus implementation. Predict the eligibility
// masks before looking at the final column: bit0 non-gated,bit1 pair,bit2 quorum.
#pragma once
#include "api.hpp"
namespace seam {
struct ReleaseStep {unsigned record;const char* event;Boundary boundary;unsigned eligible;};
inline const std::array<ReleaseStep,12> release_trace={{
 {101,"encoded",                  {false,false,false,false,7,7},0},
 {101,"enqueued",                 {false,false,false,false,7,7},0},
 {101,"stamped; replication lost", {true, false,false,false,7,7},1},
 {101,"primary lost; fenced",     {true, false,false,false,7,8},0},
 {102,"new epoch stamped",        {true, false,false,false,8,8},1},
 {102,"local persist",            {true, true, false,false,8,8},1},
 {102,"secondary paused",         {true, true, false,false,8,8},1},
 {102,"other follower persists",  {true, true, false,true, 8,8},5},
 {102,"secondary resumes/persists",{true,true,true,true,8,8},7},
 {102,"same identity retry",      {true, true, true, true, 8,8},7},
 {103,"stale leader stamped",     {true, false,false,false,7,8},0},
 {103,"stale leader persists",    {true, true, true, true, 7,8},0}
}};
}
