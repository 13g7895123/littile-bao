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
    s2317 = create_symbol_info('2317', '鴻海', 150.0)
    s2603 = create_symbol_info('2603', '長榮', 180.0)
    s2330 = create_symbol_info('2330', '台積電', 600.0)

    # 1) Setup MockAdapter
    mock_adapter = mock.MagicMock()
    type(mock_adapter).__name__ = "MockAdapter"
    
    # 2) Patch scan_daily in broker
    with mock.patch("broker.scan_daily") as mock_scan:
        # For non-fubon, scan_daily is called with DEFAULT_MOCK_INFOS
        # We make it return only 2382 based on our criteria.
        mock_scan.return_value = [s2382]
        
        # Mock load_symbol_info to return s2382 when called with ['2382']
        mock_adapter.load_symbol_info.side_effect = lambda codes: {c: s2382 for c in codes if c == '2382'}
        
        # 3) Set price filters
        win._fields["price_min"].setText("250")
        win._fields["price_max"].setText("400")
        win._fields["f9_enabled"].setChecked(True) # Force F9 enabled
        
        # 4) Run logic sequence
        win.set_broker(mock_adapter)
        cfg = win._collect_config()
                
        print(f"Config price_min: {cfg.price_min}, f9_enabled: {cfg.f9_enabled}, markets: {cfg.get_markets()}")
        summary = win._load_dashboard_preview_summary(mock_adapter, cfg)
        print(f"Summary length: {len(summary)}")
        
        win._running = False
        win._apply_dashboard_preview_summary(summary)
        win._switch_tab('dashboard')

        # 5) Verification
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
            errors.append("Table is empty.")
        if "2382" not in codes:
            errors.append("Expected code '2382' not found.")
        for unwanted in ["2317", "2603", "2330"]:
            if unwanted in codes:
                errors.append(f"Unwanted code '{unwanted}' found in table.")

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
