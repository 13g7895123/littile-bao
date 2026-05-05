import sys
import unittest.mock as mock
from PyQt6.QtWidgets import QApplication
from decimal import Decimal
import gui

def test_dashboard():
    app = QApplication.instance() or QApplication(sys.argv)
    win = gui.App()

    # Define SymbolInfo mock objects
    def create_symbol_info(code, name, price):
        si = mock.Mock()
        si.code = code
        si.name = name
        si.prev_close = Decimal(str(price))
        si.limit_up_price = Decimal(str(price * 1.1))
        si.market = "TSE"
        return si

    s2382 = create_symbol_info('2382', '研華', 350.0)

    # 1) Setup MockAdapter
    mock_adapter = mock.MagicMock()
    type(mock_adapter).__name__ = "MockAdapter"
    mock_adapter.load_symbol_info.return_value = {'2382': s2382}
    
    # Force mock gui.scan_daily as well, because of the local import in the method
    # Instead of patching broker, let's patch the name within the gui module
    
    with mock.patch("gui.scan_daily") as mock_scan:
        mock_scan.return_value = [s2382]

        # 2) Set price filters
        win._fields["price_min"].setText("250")
        win._fields["price_max"].setText("400")

        # 3) Run logic sequence
        win.set_broker(mock_adapter)
        cfg = win._collect_config()
        
        print(f"Config price_min: {cfg.price_min}, f9_enabled: {cfg.f9_enabled}")

        summary = win._load_dashboard_preview_summary(mock_adapter, cfg)
        print(f"Summary length: {len(summary)}")
        if len(summary) > 0:
            print(f"First element in summary: {summary[0]['code']}")
        
        win._running = False
        win._apply_dashboard_preview_summary(summary)
        win._switch_tab('dashboard')

        # 4) Verification
        row_count = win.monitor_table.rowCount()
        print(f"Monitor table row count: {row_count}")
        
        codes = []
        for row in range(row_count):
            item = win.monitor_table.item(row, 0)
            if item:
                codes.append(item.text())
        
        print(f"Included codes: {codes}")

        errors = []
        if row_count == 0:
            errors.append("Table is empty (monitor_table row count is 0).")
        
        if "2382" not in codes:
            errors.append(f"Expected code '2382' not found in table. Found: {codes}")
        
        if "2317" in codes:
            errors.append("Unwanted code '2317' found in table.")
        
        if "2603" in codes:
            errors.append("Unwanted code '2603' found in table.")

        if errors:
            print("\nFAILURE:")
            for err in errors:
                print(f"- {err}")
            sys.exit(1)
        else:
            print("\nSUCCESS: All dashboard verification criteria passed.")
            sys.exit(0)

if __name__ == "__main__":
    try:
        test_dashboard()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
