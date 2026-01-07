import sys
import os
sys.path.append(os.path.join(os.getcwd(), "manufacturing_pipeline"))
from src.step_processing import load_step_file

step_file = "/Users/ds/Projecten/alestest/resources/parts/fwofferte20253515bestanden/10000703900_Rev_00.step"
shape = load_step_file(step_file)

print(f"Shape type: {type(shape)}")
solids = shape.solids().vals()
print(f"Number of solids: {len(solids)}")
for i, solid in enumerate(solids):
    print(f"Solid {i}: Volume={solid.Volume():.2f}")
