# ---------- IMPORTS ----------
import kivy
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.popup import Popup
from kivy.core.window import Window
from kivy.garden.matplotlib.backend_kivyagg import FigureCanvasKivyAgg
import matplotlib.pyplot as plt
from datetime import datetime
import sqlite3

# ---------- DATABASE MANAGER ----------
class DatabaseManager:
    def __init__(self, db_path="moisture_lab.db"):
        self.db_path = db_path
        self._initialize_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _initialize_db(self):
        with self._connect() as conn:
            c = conn.cursor()
            c.execute('''
                CREATE TABLE IF NOT EXISTS pans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pan_name TEXT,
                    pan_weight REAL
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS tests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT,
                    aggregate_type TEXT,
                    pan_id INTEGER,
                    pan_name TEXT,
                    pan_weight REAL,
                    wet_gross REAL,
                    dry_gross REAL,
                    wet_net REAL,
                    dry_net REAL,
                    moisture REAL
                )
            ''')
            conn.commit()

    # Pan CRUD
    def get_pans(self):
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM pans")
            return c.fetchall()

    def add_pan(self, name, weight):
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("INSERT INTO pans (pan_name, pan_weight) VALUES (?,?)", (name, weight))
            conn.commit()

    def update_pan(self, pan_id, name, weight):
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("UPDATE pans SET pan_name=?, pan_weight=? WHERE id=?", (name, weight, pan_id))
            conn.commit()

    def delete_pan(self, pan_id):
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM pans WHERE id=?", (pan_id,))
            conn.commit()

    # Tests
    def save_test(self, date, aggregate_type, pan_id, pan_name, pan_weight, wet_gross, dry_gross, wet_net, dry_net, moisture):
        with self._connect() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO tests (date, aggregate_type, pan_id, pan_name, pan_weight,
                                   wet_gross, dry_gross, wet_net, dry_net, moisture)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            ''', (date, aggregate_type, pan_id, pan_name, pan_weight, wet_gross, dry_gross, wet_net, dry_net, moisture))
            conn.commit()

# ---------- UTILITY ----------
def compute_moisture(wet, dry, pan_weight):
    wet_net = wet - pan_weight
    dry_net = dry - pan_weight
    if dry_net <= 0:
        return 0, wet_net, dry_net
    moisture = ((wet_net - dry_net) / dry_net) * 100
    return moisture, wet_net, dry_net

# ---------- AGGREGATE CARD ----------
class AggregateCard(BoxLayout):
    def __init__(self, aggregate_type, db: DatabaseManager, **kwargs):
        super().__init__(orientation="vertical", spacing=5, padding=5, **kwargs)
        self.aggregate_type = aggregate_type
        self.db = db

        self.add_widget(Label(text=aggregate_type, font_size=18, markup=True))

        # Spinner for pan selection
        self.pans = self.db.get_pans()
        if not self.pans:
            self.db.add_pan("Pan A", 2.15)
            self.db.add_pan("Pan B", 1.98)
            self.pans = self.db.get_pans()

        self.spinner = Spinner(
            values=[f"{p[1]} ({p[2]} kg)" for p in self.pans],
            text=f"{self.pans[0][1]} ({self.pans[0][2]} kg)"
        )
        self.add_widget(self.spinner)

        # Wet & Dry gross inputs
        self.wet_input = TextInput(hint_text="Wet Gross (kg)", input_filter="float", multiline=False)
        self.dry_input = TextInput(hint_text="Dry Gross (kg)", input_filter="float", multiline=False)
        self.add_widget(self.wet_input)
        self.add_widget(self.dry_input)

        # Result label
        self.result_label = Label(text="Moisture: 0.00 %", font_size=16)
        self.add_widget(self.result_label)

        # Events
        self.wet_input.bind(text=self.calculate)
        self.dry_input.bind(text=self.calculate)
        self.spinner.bind(text=self.calculate)

    def refresh_pans(self):
        self.pans = self.db.get_pans()
        self.spinner.values = [f"{p[1]} ({p[2]} kg)" for p in self.pans]
        if self.pans:
            self.spinner.text = f"{self.pans[0][1]} ({self.pans[0][2]} kg)"

    def calculate(self, *args):
        try:
            wet = float(self.wet_input.text)
            dry = float(self.dry_input.text)
            pan_index = self.spinner.values.index(self.spinner.text)
            pan_weight = self.pans[pan_index][2]
            moisture, _, _ = compute_moisture(wet, dry, pan_weight)
            self.result_label.text = f"Moisture: {moisture:.2f} %"
        except ValueError:
            self.result_label.text = "Moisture: 0.00 %"

    def save(self, date):
        try:
            wet = float(self.wet_input.text)
            dry = float(self.dry_input.text)
            pan_index = self.spinner.values.index(self.spinner.text)
            pan = self.pans[pan_index]
            pan_id, pan_name, pan_weight = pan
            moisture, wet_net, dry_net = compute_moisture(wet, dry, pan_weight)
            self.db.save_test(date, self.aggregate_type, pan_id, pan_name, pan_weight,
                              wet, dry, wet_net, dry_net, moisture)
        except ValueError:
            pass

# ---------- PAN MANAGER ----------
class PanManager:
    def __init__(self, parent, cards, db: DatabaseManager):
        self.parent = parent
        self.cards = cards
        self.db = db
        self.layout = BoxLayout(orientation="vertical", spacing=10, padding=10)
        self.refresh_list()

        close_btn = Button(text="Close", size_hint_y=None, height=50)
        close_btn.bind(on_press=lambda x: self.popup.dismiss())
        self.layout.add_widget(close_btn)

        self.popup = Popup(title="Manage Pans", content=self.layout, size_hint=(0.9, 0.9))
        self.popup.open()

    def refresh_list(self):
        self.layout.clear_widgets()
        pans = self.db.get_pans()
        for pan in pans:
            h = BoxLayout(size_hint_y=None, height=40)
            h.add_widget(Label(text=f"{pan[1]} ({pan[2]} kg)"))
            edit_btn = Button(text="Edit", size_hint_x=None, width=80)
            del_btn = Button(text="Delete", size_hint_x=None, width=80)
            h.add_widget(edit_btn)
            h.add_widget(del_btn)
            self.layout.add_widget(h)

            edit_btn.bind(on_press=lambda x, p=pan: self.show_edit_popup(p))
            del_btn.bind(on_press=lambda x, p=pan: self.delete_pan(p))

        add_btn = Button(text="Add New Pan", size_hint_y=None, height=50)
        add_btn.bind(on_press=lambda x: self.show_edit_popup())
        self.layout.add_widget(add_btn)

    def delete_pan(self, pan):
        self.db.delete_pan(pan[0])
        self.refresh_list()
        for card in self.cards:
            card.refresh_pans()

    def show_edit_popup(self, pan=None):
        box = BoxLayout(orientation="vertical", spacing=10, padding=10)
        name_input = TextInput(hint_text="Pan Name", multiline=False)
        weight_input = TextInput(hint_text="Pan Weight (kg)", input_filter="float", multiline=False)
        if pan:
            name_input.text = pan[1]
            weight_input.text = str(pan[2])

        save_btn = Button(text="Save", size_hint_y=None, height=50)
        box.add_widget(name_input)
        box.add_widget(weight_input)
        box.add_widget(save_btn)

        popup = Popup(title="Pan Details", content=box, size_hint=(0.8, 0.5))
        popup.open()

        def save_action(instance):
            n = name_input.text.strip()
            try:
                w = float(weight_input.text.strip())
            except ValueError:
                w = 0
            if pan:
                self.db.update_pan(pan[0], n, w)
            else:
                self.db.add_pan(n, w)
            popup.dismiss()
            self.refresh_list()
            for card in self.cards:
                card.refresh_pans()

        save_btn.bind(on_press=save_action)

# ---------- HISTORY SCREEN WITH DATE RANGE ----------
class HistoryScreen:
    def __init__(self, db, parent):
        self.db = db
        self.parent = parent
        self.layout = BoxLayout(orientation="vertical", spacing=10, padding=10)

        # Aggregate selection
        self.spinner = Spinner(values=["Fine", "10mm", "20mm"], text="Fine")
        self.layout.add_widget(self.spinner)

        # Date range inputs
        date_box = BoxLayout(size_hint_y=None, height=40, spacing=5)
        self.start_input = TextInput(hint_text="Start Date YYYY-MM-DD", multiline=False)
        self.end_input = TextInput(hint_text="End Date YYYY-MM-DD", multiline=False)
        filter_btn = Button(text="Filter", size_hint_x=None, width=80)
        date_box.add_widget(self.start_input)
        date_box.add_widget(self.end_input)
        date_box.add_widget(filter_btn)
        self.layout.add_widget(date_box)

        # Graph container
        self.graph_box = BoxLayout(size_hint_y=0.8)
        self.layout.add_widget(self.graph_box)

        # Close button
        close_btn = Button(text="Close", size_hint_y=None, height=50)
        close_btn.bind(on_press=lambda x: self.popup.dismiss())
        self.layout.add_widget(close_btn)

        # Bind events
        self.spinner.bind(text=self.update_graph)
        filter_btn.bind(on_press=self.update_graph)

        # Popup
        self.popup = Popup(title="Moisture History & Trend", content=self.layout,
                           size_hint=(0.95, 0.95))
        self.popup.open()
        self.update_graph()

    def update_graph(self, *args):
        self.graph_box.clear_widgets()
        agg_type = self.spinner.text

        # Date filters
        start_date = self.start_input.text.strip()
        end_date = self.end_input.text.strip()

        # Validate dates
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") if end_date else None
        except ValueError:
            self.graph_box.add_widget(Label(text="Invalid date format! Use YYYY-MM-DD"))
            return

        # Fetch data
        with self.db._connect() as conn:
            c = conn.cursor()
            query = "SELECT date, moisture FROM tests WHERE aggregate_type=?"
            params = [agg_type]

            if start_dt and end_dt:
                query += " AND date BETWEEN ? AND ?"
                params.extend([start_date, end_date])
            elif start_dt:
                query += " AND date >= ?"
                params.append(start_date)
            elif end_dt:
                query += " AND date <= ?"
                params.append(end_date)

            query += " ORDER BY date"
            c.execute(query, tuple(params))
            data = c.fetchall()

        if not data:
            self.graph_box.add_widget(Label(text="No data for selected range"))
            return

        # Convert dates for plotting
        dates = [datetime.strptime(d[0], "%Y-%m-%d") for d in data]
        moisture = [d[1] for d in data]

        # Plot
        fig, ax = plt.subplots(figsize=(4,3))
        ax.plot(dates, moisture, marker='o', linestyle='-', color='blue')
        ax.set_title(f"{agg_type} Moisture Trend")
        ax.set_xlabel("Date")
        ax.set_ylabel("Moisture %")
        fig.autofmt_xdate(rotation=45)
        plt.tight_layout()

        self.graph_box.add_widget(FigureCanvasKivyAgg(fig))

# ---------- MAIN APP ----------
class MoistureApp(App):
    def build(self):
        self.db = DatabaseManager()
        self.current_date = datetime.now().strftime("%Y-%m-%d")  # ISO format

        root = ScrollView()
        layout = GridLayout(cols=1, spacing=10, padding=10, size_hint_y=None)
        layout.bind(minimum_height=layout.setter('height'))

        layout.add_widget(Label(text=f"Date: {self.current_date}", markup=True, font_size=20))

        # Aggregate cards
        self.cards = []
        for agg in ["Fine", "10mm", "20mm"]:
            card = AggregateCard(agg, self.db)
            layout.add_widget(card)
            self.cards.append(card)

        # Save all button
        save_btn = Button(text="Save All", size_hint_y=None, height=50)
        save_btn.bind(on_press=self.save_all)
        layout.add_widget(save_btn)

        # Manage pans button
        pan_btn = Button(text="Manage Pans", size_hint_y=None, height=50)
        pan_btn.bind(on_press=self.manage_pans)
        layout.add_widget(pan_btn)

        # View history button
        history_btn = Button(text="View History & Trend", size_hint_y=None, height=50)
        history_btn.bind(on_press=self.view_history)
        layout.add_widget(history_btn)

        root.add_widget(layout)
        return root

    def save_all(self, instance):
        for card in self.cards:
            card.save(self.current_date)
        print("All aggregates saved!")

    def manage_pans(self, instance):
        PanManager(self, self.cards, self.db)

    def view_history(self, instance):
        HistoryScreen(self.db, self)

# ---------- RUN APP ----------
if __name__ == "__main__":
    Window.size = (360, 640)  # phone-like preview
    MoistureApp().run()
