function hasMeaningfulBendGeometry(bends) {
  return (bends || []).some((bend) => {
    const angle = Number(bend?.angle)
    const radius = Number(bend?.radius)
    return (Number.isFinite(angle) && Math.abs(angle) > 0.001) || (Number.isFinite(radius) && Math.abs(radius) > 0.001)
  })
}

function meaningfulExistingBends(unfoldVisuals) {
  return (unfoldVisuals?.bends_logical || []).filter((bend) => {
    const angle = Number(bend?.angle)
    const radius = Number(bend?.radius)
    return (Number.isFinite(angle) && Math.abs(angle) > 0.001) || (Number.isFinite(radius) && Math.abs(radius) > 0.001)
  })
}

function mergeUnfoldVisuals(existingUnfold, incomingUnfold) {
  if (!incomingUnfold) return existingUnfold || null
  const existing = existingUnfold || {}
  const merged = {
    ...existing,
    ...incomingUnfold,
  }

  const incomingBends = Array.isArray(incomingUnfold?.bends_logical) ? incomingUnfold.bends_logical : []
  if (hasMeaningfulBendGeometry(incomingBends)) {
    merged.bends_logical = incomingBends
    return merged
  }

  const fallbackBends = meaningfulExistingBends(existing)
  if (incomingBends.length > 0 && fallbackBends.length > 0) {
    merged.bends_logical = incomingBends.map((bend, index) => {
      const fallback = fallbackBends[index] || fallbackBends[fallbackBends.length - 1] || {}
      const angle = Number(bend?.angle)
      const radius = Number(bend?.radius)
      return {
        ...fallback,
        ...bend,
        angle: Number.isFinite(angle) && Math.abs(angle) > 0.001 ? bend.angle : fallback.angle,
        radius: Number.isFinite(radius) && Math.abs(radius) > 0.001 ? bend.radius : fallback.radius,
        type: bend?.type || fallback.type,
        id: bend?.id || fallback.id || index + 1,
      }
    })
    if (!merged.bend_angles_erp || merged.bend_angles_erp.length === 0) {
      merged.bend_angles_erp = merged.bends_logical
        .map((bend) => bend?.angle)
        .filter((angle) => Number.isFinite(Number(angle)))
    }
    return merged
  }

  if ((!incomingBends || incomingBends.length === 0) && fallbackBends.length > 0) {
    merged.bends_logical = fallbackBends
  }

  return merged
}

export { hasMeaningfulBendGeometry, meaningfulExistingBends, mergeUnfoldVisuals }