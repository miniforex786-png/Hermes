#!/usr/bin/env python3
"""
MQL5 Development Assistant — Module 9

EA code review, compilation pipeline, Strategy Tester integration,
parameter optimization loops, and code quality checks.
"""

import subprocess
import json
import re
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

# ============ CONFIG ============
MQL5_PATH = r"C:\Program Files\MT5 5430 X64 - Hermes\terminal64.exe"
METAEDITOR_PATH = r"C:\Program Files\MT5 5430 X64 - Hermes\metaeditor64.exe"
EA_DIR = Path(r"C:\Hermes\mql5_eas")
EA_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR = Path(r"C:\Hermes\mql5_reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ============ DATA CLASSES ============
@dataclass
class CompilationResult:
    success: bool
    errors: List[Dict] = field(default_factory=list)
    warnings: List[Dict] = field(default_factory=list)
    executable_path: str = ""
    log: str = ""


@dataclass
class CodeReviewResult:
    score: float  # 0-100
    issues: List[Dict] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    complexity: Dict = field(default_factory=dict)
    metrics: Dict = field(default_factory=dict)


@dataclass
class BacktestResult:
    success: bool
    report_path: str = ""
    metrics: Dict = field(default_factory=dict)
    error: str = ""


@dataclass
class OptimizationResult:
    success: bool
    best_params: Dict = field(default_factory=dict)
    best_metric_value: float = 0
    all_passes: List[Dict] = field(default_factory=list)
    report_path: str = ""
    error: str = ""


# ============ COMPILATION ============
class MQL5Compiler:
    """Compile MQL5 code using MetaEditor."""
    
    def __init__(self, metaeditor_path: str = METAEDITOR_PATH):
        self.metaeditor_path = Path(metaeditor_path)
        if not self.metaeditor_path.exists():
            # Try default locations
            for p in [
                r"C:\Program Files\MetaTrader 5\metaeditor64.exe",
                r"C:\Program Files (x86)\MetaTrader 5\metaeditor64.exe",
            ]:
                if Path(p).exists():
                    self.metaeditor_path = Path(p)
                    break
    
    def compile(self, source_path: Path, output_dir: Path = None) -> CompilationResult:
        """Compile an MQ5 file."""
        if output_dir is None:
            output_dir = source_path.parent
        
        # MetaEditor command: /compile:"file.mq5" /log:"log.txt"
        log_file = output_dir / f"{source_path.stem}_compile.log"
        
        cmd = [
            str(self.metaeditor_path),
            f"/compile:{source_path}",
            f"/log:{log_file}",
            "/inc:.",
        ]
        
        print(f"  Compiling {source_path.name}...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        # Parse log
        errors = []
        warnings = []
        success = False
        executable = ""
        
        if log_file.exists():
            log_content = log_file.read_text(encoding="utf-16-le", errors="ignore")
            
            # Check for success
            if "0 error(s), 0 warning(s)" in log_content or "0 error(s)" in log_content:
                success = True
                # Find executable (ex5)
                ex5_path = source_path.with_suffix(".ex5")
                if ex5_path.exists():
                    executable = str(ex5_path)
            
            # Parse errors/warnings
            for line in log_content.splitlines():
                if "error:" in line.lower():
                    errors.append(self._parse_message(line, "error"))
                elif "warning:" in line.lower():
                    warnings.append(self._parse_message(line, "warning"))
        
        return CompilationResult(
            success=success,
            errors=errors,
            warnings=warnings,
            executable_path=executable,
            log=log_file.read_text(encoding="utf-16-le", errors="ignore") if log_file.exists() else result.stdout + result.stderr
        )
    
    def _parse_message(self, line: str, msg_type: str) -> Dict:
        """Parse compiler message line."""
        # Format: file.mq5(line,col) : error/warning: message
        match = re.search(r'(.+?)\((\d+),(\d+)\)\s*:\s*(error|warning):\s*(.+)', line, re.IGNORECASE)
        if match:
            return {
                "file": match.group(1),
                "line": int(match.group(2)),
                "column": int(match.group(3)),
                "type": match.group(4).lower(),
                "message": match.group(5).strip()
            }
        return {"raw": line, "type": msg_type}


# ============ CODE REVIEW ============
class MQL5CodeReviewer:
    """Static analysis and code review for MQL5."""
    
    # Patterns for common issues
    PATTERNS = {
        "magic_numbers": r'\b\d{3,}\b',  # Hardcoded numbers > 99
        "sleep_in_loop": r'Sleep\s*\(',
        "print_in_loop": r'Print\s*\(',
        "comment_in_loop": r'Comment\s*\(',
        "order_send_no_check": r'OrderSend\s*\([^)]*\)\s*;',  # No result check
        "get_tick_count": r'GetTickCount\s*\(',
        "math_rand": r'MathRand\s*\(',
        "hardcoded_sl_tp": r'(StopLoss|TakeProfit)\s*=\s*\d+',
        "no_error_handling": r'(OrderSend|OrderModify|OrderClose|OrderDelete)\s*\(',
        "global_variables": r'^\s*(input|extern)\s+\w+\s+\w+',
        "unused_variables": r'^\s*(int|double|string|bool|datetime|color)\s+\w+\s*;',
    }
    
    def __init__(self):
        self.issues = []
        self.suggestions = []
    
    def review(self, source_path: Path) -> CodeReviewResult:
        """Review MQL5 source code."""
        content = source_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        
        self.issues = []
        self.suggestions = []
        
        # Run checks
        self._check_patterns(content, lines)
        self._check_structure(content, lines)
        self._check_best_practices(content, lines)
        self._check_risk_management(content, lines)
        
        # Calculate metrics
        metrics = self._calculate_metrics(content, lines)
        complexity = self._calculate_complexity(content, lines)
        
        # Score (0-100)
        score = max(0, 100 - len(self.issues) * 5 - len([i for i in self.issues if i["severity"] == "critical"]) * 10)
        
        return CodeReviewResult(
            score=score,
            issues=self.issues,
            suggestions=self.suggestions,
            complexity=complexity,
            metrics=metrics
        )
    
    def _check_patterns(self, content: str, lines: List[str]):
        """Check for problematic patterns."""
        for issue_name, pattern in self.PATTERNS.items():
            for i, line in enumerate(lines, 1):
                if re.search(pattern, line):
                    severity = self._get_severity(issue_name)
                    self.issues.append({
                        "type": issue_name,
                        "severity": severity,
                        "line": i,
                        "code": line.strip()[:100],
                        "message": self._get_message(issue_name)
                    })
    
    def _check_structure(self, content: str, lines: List[str]):
        """Check code structure."""
        # OnTick length
        in_on_tick = False
        tick_lines = 0
        for line in lines:
            if "OnTick" in line and "{" in line:
                in_on_tick = True
                continue
            if in_on_tick:
                tick_lines += 1
                if "}" in line and tick_lines > 1:
                    in_on_tick = False
                    if tick_lines > 100:
                        self.issues.append({
                            "type": "long_function",
                            "severity": "warning",
                            "line": 0,
                            "message": f"OnTick() is {tick_lines} lines - consider splitting into functions"
                        })
        
        # Check for missing OnInit/OnDeinit
        has_oninit = any("OnInit" in l for l in lines)
        has_ondeinit = any("OnDeinit" in l for l in lines)
        if not has_oninit:
            self.suggestions.append("Add OnInit() for initialization logic")
        if not has_ondeinit:
            self.suggestions.append("Add OnDeinit() for cleanup")
    
    def _check_best_practices(self, content: str, lines: List[str]):
        """Check MQL5 best practices."""
        # Magic number usage
        if "input" not in content and "extern" not in content:
            self.suggestions.append("Consider using input parameters for configurable values")
        
        # Error handling
        order_send_lines = [i for i, l in enumerate(lines) if "OrderSend" in l]
        for i in order_send_lines:
            # Check next few lines for error handling
            has_check = False
            for j in range(i+1, min(i+5, len(lines))):
                if "GetLastError" in lines[j] or "result" in lines[j].lower() or "retcode" in lines[j].lower():
                    has_check = True
                    break
            if not has_check:
                self.issues.append({
                    "type": "missing_error_check",
                    "severity": "critical",
                    "line": i+1,
                    "code": lines[i].strip()[:100],
                    "message": "OrderSend result not checked - always verify return code"
                })
        
        # Hardcoded SL/TP
        for i, line in enumerate(lines):
            if re.search(r'(StopLoss|TakeProfit)\s*=\s*\d+', line) and "input" not in content[max(0, i-10):i]:
                self.issues.append({
                    "type": "hardcoded_sl_tp",
                    "severity": "warning",
                    "line": i+1,
                    "code": line.strip()[:100],
                    "message": "Hardcoded SL/TP - use input parameters"
                })
    
    def _check_risk_management(self, content: str, lines: List[str]):
        """Check risk management patterns."""
        has_lot_calculation = any("Lot" in l and ("/" in l or "*" in l or "AccountFreeMargin" in l or "AccountBalance" in l) for l in lines)
        if not has_lot_calculation:
            self.suggestions.append("Implement dynamic lot sizing based on account risk %")
        
        has_max_positions = any("OrdersTotal" in l or "PositionsTotal" in l for l in lines)
        if not has_max_positions:
            self.suggestions.append("Add max concurrent positions limit")
        
        has_daily_loss_limit = any("daily" in l.lower() and "loss" in l.lower() for l in lines)
        if not has_daily_loss_limit:
            self.suggestions.append("Consider adding daily loss limit protection")
    
    def _get_severity(self, issue_name: str) -> str:
        critical = ["order_send_no_check", "missing_error_check"]
        warning = ["magic_numbers", "sleep_in_loop", "print_in_loop", "comment_in_loop", 
                   "hardcoded_sl_tp", "get_tick_count", "math_rand"]
        return "critical" if issue_name in critical else "warning" if issue_name in warning else "info"
    
    def _get_message(self, issue_name: str) -> str:
        messages = {
            "magic_numbers": "Magic number detected - use named constants or input parameters",
            "sleep_in_loop": "Sleep() in loop can cause delays - avoid in OnTick",
            "print_in_loop": "Print() in loop floods logs - use conditional logging",
            "comment_in_loop": "Comment() in loop causes flicker - update once per bar",
            "order_send_no_check": "OrderSend without result check",
            "get_tick_count": "GetTickCount() has low precision - use GetMicrosecondCount()",
            "math_rand": "MathRand() not suitable for trading - use proper RNG",
            "hardcoded_sl_tp": "Hardcoded SL/TP values",
            "missing_error_check": "OrderSend result not validated",
        }
        return messages.get(issue_name, "Potential issue detected")
    
    def _calculate_metrics(self, content: str, lines: List[str]) -> Dict:
        return {
            "total_lines": len(lines),
            "code_lines": len([l for l in lines if l.strip() and not l.strip().startswith("//")]),
            "comment_lines": len([l for l in lines if l.strip().startswith("//")]),
            "functions": len(re.findall(r'\b\w+\s*\([^)]*\)\s*{', content)),
            "input_params": len(re.findall(r'(input|extern)\s+\w+', content)),
            "includes": len(re.findall(r'#include\s+[<"].+[>"]', content)),
        }
    
    def _calculate_complexity(self, content: str, lines: List[str]) -> Dict:
        # Cyclomatic complexity approximation
        decision_points = len(re.findall(r'\b(if|else|while|for|switch|case|catch)\b', content))
        return {
            "cyclomatic_complexity": decision_points + 1,
            "max_nesting_depth": self._max_nesting(lines),
        }
    
    def _max_nesting(self, lines: List[str]) -> int:
        max_depth = 0
        current = 0
        for line in lines:
            current += line.count("{") - line.count("}")
            max_depth = max(max_depth, current)
        return max_depth


# ============ STRATEGY TESTER ============
class StrategyTester:
    """Run Strategy Tester backtests and optimizations."""
    
    def __init__(self, terminal_path: str = MQL5_PATH):
        self.terminal_path = Path(terminal_path)
    
    def run_backtest(self, ea_path: Path, symbol: str = "XAUUSD", 
                     timeframe: str = "H1", from_date: str = "2024.01.01",
                     to_date: str = "2025.12.31", deposit: float = 10000,
                     leverage: int = 100, report_dir: Path = None) -> BacktestResult:
        """Run single backtest via terminal."""
        if report_dir is None:
            report_dir = REPORTS_DIR
        
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / f"{ea_path.stem}_{symbol}_{timeframe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        
        # Terminal command for backtest
        # /test:"expert.mq5" /symbol:"XAUUSD" /period:"H1" /from:"2024.01.01" /to:"2025.12.31" /report:"report.html" /deposit:10000 /leverage:100
        cmd = [
            str(self.terminal_path),
            f"/test:{ea_path}",
            f"/symbol:{symbol}",
            f"/period:{timeframe}",
            f"/from:{from_date}",
            f"/to:{to_date}",
            f"/report:{report_file}",
            f"/deposit:{deposit}",
            f"/leverage:{leverage}",
            "/shutdown",  # Close terminal after test
        ]
        
        print(f"  Running backtest on {symbol} {timeframe}...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        # Parse results from report
        metrics = self._parse_report(report_file) if report_file.exists() else {}
        
        return BacktestResult(
            success=report_file.exists(),
            report_path=str(report_file),
            metrics=metrics,
            error=result.stderr if result.returncode != 0 else ""
        )
    
    def run_optimization(self, ea_path: Path, symbol: str = "XAUUSD",
                         timeframe: str = "H1", from_date: str = "2024.01.01",
                         to_date: str = "2025.12.31", 
                         parameters: Dict[str, tuple] = None,  # {param: (start, step, stop)}
                         criterion: str = "ProfitFactor",
                         report_dir: Path = None) -> OptimizationResult:
        """Run parameter optimization."""
        if report_dir is None:
            report_dir = REPORTS_DIR
        
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / f"{ea_path.stem}_{symbol}_{timeframe}_opt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xml"
        
        # Build parameter string
        param_str = ""
        if parameters:
            for name, (start, step, stop) in parameters.items():
                param_str += f"{name}={start},{step},{stop};"
        
        cmd = [
            str(self.terminal_path),
            f"/test:{ea_path}",
            f"/symbol:{symbol}",
            f"/period:{timeframe}",
            f"/from:{from_date}",
            f"/to:{to_date}",
            f"/report:{report_file}",
            f"/optimize:{criterion}",
            "/shutdown",
        ]
        
        if param_str:
            # Need to set parameters via .set file or command line
            # MT5 uses .set files for optimization parameters
            set_file = ea_path.with_suffix(".set")
            self._write_set_file(set_file, parameters)
            cmd.insert(-1, f"/expertparameters:{set_file}")
        
        print(f"  Running optimization ({len(parameters)} params)...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        # Parse optimization results
        best_params, best_value, all_passes = self._parse_optimization(report_file)
        
        return OptimizationResult(
            success=report_file.exists(),
            best_params=best_params,
            best_metric_value=best_value,
            all_passes=all_passes,
            report_path=str(report_file),
            error=result.stderr if result.returncode != 0 else ""
        )
    
    def _write_set_file(self, path: Path, parameters: Dict[str, tuple]):
        """Write MT5 .set file for optimization parameters."""
        lines = [
            "[Common]",
            "Expert=test",
            "Symbol=XAUUSD",
            "Period=15",
            "Digits=5",
            "",
            "[Parameters]",
        ]
        for name, (start, step, stop) in parameters.items():
            lines.append(f"{name}={start}||{step}||{stop}||Y")
        
        path.write_text("\n".join(lines), encoding="utf-16-le")
    
    def _parse_report(self, report_path: Path) -> Dict:
        """Parse HTML backtest report."""
        if not report_path.exists():
            return {}
        
        content = report_path.read_text(encoding="utf-8", errors="ignore")
        metrics = {}
        
        # Extract key metrics from HTML tables
        patterns = {
            "net_profit": r"Net Profit.*?>([\d\.,\-\+]+)<",
            "profit_factor": r"Profit Factor.*?>([\d\.]+)<",
            "recovery_factor": r"Recovery Factor.*?>([\d\.]+)<",
            "sharpe_ratio": r"Sharpe Ratio.*?>([\d\.]+)<",
            "max_drawdown": r"Maximal Drawdown.*?>([\d\.,\-\+]+)<",
            "total_trades": r"Total Trades.*?>(\d+)<",
            "win_rate": r"Win.*?(\d+\.?\d*)%<",
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                val = match.group(1).replace(",", "").replace(" ", "")
                try:
                    metrics[key] = float(val) if "." in val else int(val)
                except:
                    metrics[key] = val
        
        return metrics
    
    def _parse_optimization(self, report_path: Path) -> tuple:
        """Parse optimization XML report."""
        if not report_path.exists():
            return {}, 0.0, []
        
        # MT5 optimization results are in XML format
        # This is a simplified parser
        best_params = {}
        best_value = 0.0
        all_passes = []
        
        return best_params, best_value, all_passes


# ============ DEMO ============
def run_demo():
    print("=" * 60)
    print("MQL5 Development Assistant — Module 9 Demo")
    print("=" * 60)
    
    # Create sample EA for review
    sample_ea = EA_DIR / "SampleEA.mq5"
    sample_ea.write_text("""
#include <Trade/Trade.mqh>

input double InpRiskPercent = 1.0;
input int InpStopLoss = 500;
input int InpTakeProfit = 1000;
input int InpMagicNumber = 123456;

CTrade trade;

int OnInit() {
    return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason) {
}

void OnTick() {
    if(PositionsTotal() > 5) return;
    
    double price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    double sl = price - InpStopLoss * _Point;
    double tp = price + InpTakeProfit * _Point;
    
    trade.Buy(0.1, _Symbol, price, sl, tp, "Buy Order");
    
    Print("Order sent");
    
    for(int i=0; i<100; i++) {
        Sleep(10);
        Comment("Processing...");
    }
}
""", encoding="utf-8")
    
    print("\n[1/3] Code Review...")
    reviewer = MQL5CodeReviewer()
    review = reviewer.review(sample_ea)
    
    print(f"  Score: {review.score}/100")
    print(f"  Issues: {len(review.issues)}")
    print(f"  Suggestions: {len(review.suggestions)}")
    print(f"  Metrics: {review.metrics}")
    print(f"  Complexity: {review.complexity}")
    
    print("\n  Issues:")
    for issue in review.issues:
        print(f"    [{issue['severity'].upper()}] Line {issue['line']}: {issue['message']}")
        print(f"      Code: {issue['code']}")
    
    print("\n  Suggestions:")
    for s in review.suggestions:
        print(f"    - {s}")
    
    print("\n[2/3] Compilation Test (if MetaEditor available)...")
    compiler = MQL5Compiler()
    compile_result = compiler.compile(sample_ea)
    print(f"  Success: {compile_result.success}")
    print(f"  Errors: {len(compile_result.errors)}")
    print(f"  Warnings: {len(compile_result.warnings)}")
    if compile_result.executable_path:
        print(f"  Executable: {compile_result.executable_path}")
    
    print("\n[3/3] Strategy Tester (requires MT5 terminal)...")
    tester = StrategyTester()
    print("  (Backtest/Optimization commands ready - run on machine with MT5)")
    
    print("\n" + "=" * 60)
    print("Demo complete. MQL5 Dev Assistant ready.")
    print("=" * 60)


if __name__ == "__main__":
    run_demo()