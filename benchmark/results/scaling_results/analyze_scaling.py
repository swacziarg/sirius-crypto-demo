import pandas as pd
import glob
import os
import matplotlib.pyplot as plt

INPUT_DIR = "."
OUTPUT_DIR = "./analysis_output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================================
# SCALE DETECTION (FIXED — more robust)
# ============================================================
def extract_scale(filename):
    name = os.path.basename(filename)

    if "JAN-FEB-2025" in name:
        return "2_month"
    elif "FEB-2025" in name:
        return "1_month"
    elif "FEB-W1" in name:
        return "1_week"
    elif "FEB-07" in name:
        return "1_day"
    else:
        return "unknown"

# ============================================================
# VERSION DETECTION (NEW)
# ============================================================
def extract_version(query):
    if query == "Q01":
        return "V0"
    elif "_V1" in query:
        return "V1"
    elif "_V3" in query:
        return "V3"
    else:
        return "unknown"

# ============================================================
# LOAD
# ============================================================
files = glob.glob(f"{INPUT_DIR}/*.csv")
print("Found files:", files)

dfs = []
for f in files:
    df = pd.read_csv(f)
    df["scale"] = extract_scale(f)
    df["version"] = df["query"].apply(extract_version)
    df["file"] = os.path.basename(f)
    dfs.append(df)

df = pd.concat(dfs, ignore_index=True)

# ============================================================
# CLEAN
# ============================================================
df = df[~df["run"].astype(str).str.contains("warmup")]
df = df[df["time_ms"] != "FAILED"]
df["time_ms"] = df["time_ms"].astype(float)

# ============================================================
# 1. PER QUERY (UNCHANGED)
# ============================================================
agg_query = (
    df.groupby(["scale", "query", "engine"])
    .agg(median_ms=("time_ms", "median"))
    .reset_index()
)

pivot_query = agg_query.pivot_table(
    index=["scale", "query"],
    columns="engine",
    values="median_ms"
).reset_index()

# ============================================================
# 2. AGGREGATE BY VERSION (THIS IS WHAT YOU WANT)
# ============================================================
agg_version = (
    df.groupby(["scale", "version", "engine"])
    .agg(median_ms=("time_ms", "median"))
    .reset_index()
)

pivot_version = agg_version.pivot_table(
    index=["scale", "version"],
    columns="engine",
    values="median_ms"
).reset_index()

# ============================================================
# 3. GLOBAL AGGREGATION (ALL QUERIES)
# ============================================================
agg_global = (
    df.groupby(["scale", "engine"])
    .agg(median_ms=("time_ms", "median"))
    .reset_index()
)

pivot_global = agg_global.pivot_table(
    index="scale",
    columns="engine",
    values="median_ms"
).reset_index()

# ============================================================
# SPEEDUPS (apply to all pivots)
# ============================================================
def add_speedups(pivot):
    if "cpu" in pivot.columns and "gpu_processing" in pivot.columns:
        pivot["speedup_gpu_processing"] = pivot["cpu"] / pivot["gpu_processing"]
    if "cpu" in pivot.columns and "gpu_execution" in pivot.columns:
        pivot["speedup_gpu_execution"] = pivot["cpu"] / pivot["gpu_execution"]
    return pivot

pivot_query = add_speedups(pivot_query)
pivot_version = add_speedups(pivot_version)
pivot_global = add_speedups(pivot_global)

# ============================================================
# SORT SCALE (FIXED ORDER)
# ============================================================
scale_order = ["1_day", "1_week", "1_month", "2_month"]

for table in [pivot_query, pivot_version, pivot_global]:
    table["scale"] = pd.Categorical(table["scale"], categories=scale_order, ordered=True)
    table.sort_values("scale", inplace=True)

# ============================================================
# SAVE
# ============================================================
pivot_query.to_csv(f"{OUTPUT_DIR}/comparison_per_query.csv", index=False)
pivot_version.to_csv(f"{OUTPUT_DIR}/comparison_by_version.csv", index=False)
pivot_global.to_csv(f"{OUTPUT_DIR}/comparison_global.csv", index=False)

print("Saved all outputs.")

# ============================================================
# PLOTS
# ============================================================

# --- GLOBAL SCALING (MOST IMPORTANT)
plt.figure()
for col in ["cpu", "gpu_processing", "gpu_execution"]:
    if col in pivot_global.columns:
        plt.plot(pivot_global["scale"], pivot_global[col], marker="o", label=col)

plt.title("Overall Scaling")
plt.xlabel("Scale")
plt.ylabel("Latency (ms)")
plt.legend()
plt.tight_layout()
plt.savefig(f"{OUTPUT_DIR}/global_scaling.png")
plt.close()

# --- VERSION SCALING (KEY INSIGHT)
for v in pivot_version["version"].unique():
    subset = pivot_version[pivot_version["version"] == v]

    plt.figure()
    for col in ["cpu", "gpu_processing", "gpu_execution"]:
        if col in subset.columns:
            plt.plot(subset["scale"], subset[col], marker="o", label=col)

    plt.title(f"{v} Scaling")
    plt.xlabel("Scale")
    plt.ylabel("Latency (ms)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/{v}_scaling.png")
    plt.close()

print("Plots generated.")