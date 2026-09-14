import React from "react";
import { AlertTriangle, CheckCircle, ShieldAlert, Clock, ShieldCheck } from "lucide-react";

const STYLES = {
  High: "bg-red-50 text-red-700 ring-1 ring-red-200/80 shadow-xs",
  REJECT: "bg-rose-50 text-rose-700 ring-1 ring-rose-300/80 shadow-xs font-extrabold",
  Medium: "bg-amber-50 text-amber-700 ring-1 ring-amber-200/80 shadow-xs",
  REVIEW: "bg-amber-50 text-amber-800 ring-1 ring-amber-300/80 shadow-xs font-extrabold",
  Low: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200/80 shadow-xs",
  APPROVE: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-300/80 shadow-xs font-extrabold",
};

const DOT = {
  High: "bg-red-500 animate-pulse",
  REJECT: "bg-rose-600 animate-pulse",
  Medium: "bg-amber-500",
  REVIEW: "bg-amber-500",
  Low: "bg-emerald-500",
  APPROVE: "bg-emerald-500",
};

export default function Badge({ value, showIcon = true }) {
  const cls = STYLES[value] || "bg-slate-100 text-slate-700 ring-1 ring-slate-200";
  const dot = DOT[value] || "bg-slate-400";

  const renderIcon = () => {
    if (!showIcon) return null;
    switch (value) {
      case "High":
      case "REJECT":
        return <ShieldAlert className="w-3.5 h-3.5 text-rose-600 flex-shrink-0" />;
      case "Medium":
      case "REVIEW":
        return <Clock className="w-3.5 h-3.5 text-amber-600 flex-shrink-0" />;
      case "Low":
      case "APPROVE":
        return <ShieldCheck className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />;
      default:
        return <span className={`w-1.5 h-1.5 rounded-full ${dot} flex-shrink-0`}></span>;
    }
  };

  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs tracking-wide ${cls}`}>
      {renderIcon()}
      <span>{value}</span>
    </span>
  );
}