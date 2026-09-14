const STYLES = {
  High:     "bg-red-50 text-red-700 ring-1 ring-red-200",
  REJECT:   "bg-red-50 text-red-700 ring-1 ring-red-200",
  Medium:   "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
  REVIEW:   "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
  Low:      "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
  APPROVE:  "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
};
const DOT = {
  High: "bg-red-500", REJECT: "bg-red-500",
  Medium: "bg-amber-500", REVIEW: "bg-amber-500",
  Low: "bg-emerald-500", APPROVE: "bg-emerald-500",
};

export default function Badge({ value }) {
  const cls = STYLES[value] || "bg-gray-100 text-gray-600 ring-1 ring-gray-200";
  const dot = DOT[value] || "bg-gray-400";
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold ${cls}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dot}`}></span>
      {value}
    </span>
  );
}
