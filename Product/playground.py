import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, filedialog
from typing import List, Optional, Dict
import math
import re
import uuid
import json
import os

# ==========================================
# DOMAIN MODELS (OSLC Concepts)
# ==========================================

class ArtifactConcept:
    """Represents the unversioned identity of an engineering resource (e.g., REQ-101)."""
    def __init__(self, name: str, tool: 'Tool'):
        self.id: str = f"CON::{uuid.uuid4().hex[:8]}"
        self.name: str = name
        self.tool: 'Tool' = tool
        self.versions: List['ArtifactVersion'] = []

class ArtifactVersion:
    """Represents an immutable specific state of a Concept (e.g., REQ-101 v1.0)."""
    def __init__(self, concept: ArtifactConcept, version_str: str, predecessor: Optional['ArtifactVersion'] = None):
        self.id: str = f"ART::{uuid.uuid4().hex[:8]}"
        self.concept: ArtifactConcept = concept
        self.version_str: str = version_str
        self.predecessor: Optional['ArtifactVersion'] = predecessor
        self.links: List['ArtifactVersion'] = []

    @property
    def name(self) -> str:
        return f"{self.concept.name} ({self.version_str})"

class LocalConfig:
    """Represents an OSLC Version Resource context (Stream or Baseline)."""
    def __init__(self, name: str, config_type: str, tool: 'Tool', derived_from: Optional['LocalConfig'] = None):
        self.name: str = name
        self.config_type: str = config_type  # 'Stream' or 'Baseline'
        self.tool: 'Tool' = tool
        self.id: str = f"{tool.name}::{name}"
        self.derived_from: Optional['LocalConfig'] = derived_from
        
        # OSLC Architecture: A Config is just a dictionary of Concept -> Active Version
        self.selections: Dict[str, ArtifactVersion] = {}
        
        # Layout & Dimensions
        self.offset_x: float = 0.0
        self.offset_y: float = 0.0
        self.width: float = 200.0
        self.height: float = 80.0

    @property
    def artifacts(self) -> List[ArtifactVersion]:
        """Returns the currently active versions in this configuration context."""
        return list(self.selections.values())

class Tool:
    """Represents an OSLC Contributor Application (e.g., DNG, ETM)."""
    def __init__(self, name: str):
        self.name: str = name
        self.configs: List[LocalConfig] = []
        self.concepts: List[ArtifactConcept] = []
        
        self.x: float = 0.0
        self.y: float = 0.0
        self.width: float = 260.0
        self.height: float = 250.0
        self.display_horizontal: bool = False
        
        # UI Assets
        self.icon_path: Optional[str] = None
        self.icon_image: Optional[tk.PhotoImage] = None

    def add_config(self, name: str, config_type: str, derived_from: Optional[LocalConfig] = None) -> LocalConfig:
        config = LocalConfig(name, config_type, self, derived_from)
        self.configs.append(config)
        return config

class GlobalConfig:
    """Represents the GCM Aggregator component tree."""
    def __init__(self, name: str, config_type: str, derived_from: Optional['GlobalConfig'] = None):
        self.name: str = name
        self.config_type: str = config_type
        self.id: str = f"GC::{uuid.uuid4().hex[:8]}"
        self.derived_from: Optional['GlobalConfig'] = derived_from
        self.linked_configs: Dict[str, LocalConfig] = {} 
        
        self.x: float = 0.0
        self.y: float = 0.0
        self.width: float = 140.0
        self.height: float = 65.0

# ==========================================
# APPLICATION CONTROLLER & VIEW
# ==========================================

class OSLCPlaygroundApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("OSLC Global Configuration Management - Enterprise Architecture")
        self.root.geometry("1500x900")
        self.root.configure(bg="#eceff1")

        # System State
        self.tools: List[Tool] = []
        self.global_configs: List[GlobalConfig] = []
        self.active_gc: Optional[GlobalConfig] = None 
        self.link_source_artifact: Optional[ArtifactVersion] = None
        self.link_pull_target_conf: Optional[LocalConfig] = None
        
        # View & Visibility Options
        self.visibility = {
            "Stream": True,
            "Baseline": True,
            "Branch": True,
            "Context Resolution": True,
            "Artifact Link": True
        }
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        
        # Interaction State
        self.is_panning = False
        self.dragging_tool = None
        self.resizing_tool = None
        self.dragging_conf = None
        self.resizing_conf = None
        self.dragging_gc = None
        self.resizing_gc = None
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.orig_tool_x = self.orig_tool_y = self.orig_tool_w = self.orig_tool_h = 0
        self.orig_conf_offset_x = self.orig_conf_offset_y = self.orig_conf_w = self.orig_conf_h = 0
        self.orig_gc_x = self.orig_gc_y = self.orig_gc_w = self.orig_gc_h = 0
        self.layout_needs_init = True
        
        # Render Tracking (Context-Aware Canvas Coords)
        self.active_gc_link_coords: Dict[str, tuple] = {}
        self.render_coords: Dict[tuple, tuple] = {} # (conf_id, art_id) -> (x, y)

        self._init_styles()
        self._initialize_default_data()
        self._setup_ui()
        
        self.canvas.bind("<Configure>", self.redraw_canvas)
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Button-4>", self.on_mouse_wheel) 
        self.canvas.bind("<Button-5>", self.on_mouse_wheel) 

    def _init_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TFrame", background="#eceff1")
        style.configure("TLabelframe", background="#eceff1", font=("Segoe UI", 11, "bold"), foreground="#263238")
        style.configure("TLabelframe.Label", background="#eceff1")
        style.configure("TButton", font=("Segoe UI", 9), padding=5)
        style.configure("Action.TButton", background="#2196f3", foreground="white")
        style.map("Action.TButton", background=[("active", "#1976d2")])
        style.configure("TLabel", background="#eceff1", font=("Segoe UI", 10))

    def _initialize_default_data(self):
        for t_name in ["Requirements (DNG)", "Architecture (RMM)", "Implementation (IDE)", "Testing (ETM)"]:
            self.tools.append(Tool(t_name))

    def _setup_ui(self):
        self.left_panel = ttk.Frame(self.root, width=320, relief=tk.RAISED, borderwidth=1)
        self.left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        self.left_panel.pack_propagate(False)

        self.canvas_panel = ttk.Frame(self.root)
        self.canvas_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # PANEL 0: File Operations
        frame_file = ttk.Frame(self.left_panel)
        frame_file.pack(fill=tk.X, padx=10, pady=(10, 0))
        ttk.Button(frame_file, text="💾 Save Config", command=self.save_state).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,2))
        ttk.Button(frame_file, text="📂 Load Config", command=self.load_state).pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(2,0))

        # PANEL 1: Local Tool Management
        frame_tools = ttk.LabelFrame(self.left_panel, text="1. Domain Tools")
        frame_tools.pack(fill=tk.X, padx=10, pady=(10, 5))
        ttk.Button(frame_tools, text="➕ Add Custom Tool", command=self.create_tool).pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(frame_tools, text="🌱 Add Stream to Tool", command=lambda: self.create_local_config('Stream')).pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(frame_tools, text="🔄 Auto-Arrange Layout", command=self.arrange_tools).pack(fill=tk.X, padx=5, pady=(15,2))

        # PANEL 1.5: Artifacts
        frame_arts = ttk.LabelFrame(self.left_panel, text="1.5. Artifacts & Linking")
        frame_arts.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(frame_arts, text="📄 Create Artifact", command=self.create_artifact).pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(frame_arts, text="• [↔/↕] in headers toggle Tree View\n• [⚙️] opens Context Menu\n• Drag Tool/Config bodies to move\n• Drag bottom-right corners to resize", font=("Segoe UI", 8, "italic")).pack(padx=5, pady=2)

        # PANEL 2: GCM Aggregator Management
        frame_gc = ttk.LabelFrame(self.left_panel, text="2. Global Config (Aggregator)")
        frame_gc.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(frame_gc, text="🌊 Create GC Stream", command=lambda: self.create_global_config('Stream')).pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(frame_gc, text="🔗 Bind Local Config to GC", style="Action.TButton", command=self.link_to_gc).pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(frame_gc, text="📸 Snap GC Baseline", command=self.snap_gc_baseline).pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(frame_gc, text="🌿 Branch GC", command=self.branch_gc).pack(fill=tk.X, padx=5, pady=2)

        # PANEL 3: Context Resolution
        frame_context = ttk.LabelFrame(self.left_panel, text="3. Context Resolution")
        frame_context.pack(fill=tk.X, padx=10, pady=10)
        self.gc_combobox = ttk.Combobox(frame_context, state="readonly", values=["None"])
        self.gc_combobox.set("None")
        self.gc_combobox.pack(fill=tk.X, padx=5, pady=5)
        self.gc_combobox.bind("<<ComboboxSelected>>", self.change_context)

        # PANEL 4: View Controls
        frame_view = ttk.LabelFrame(self.left_panel, text="4. Canvas Controls")
        frame_view.pack(fill=tk.X, padx=10, pady=10)
        btn_frame = ttk.Frame(frame_view)
        btn_frame.pack(pady=5)
        ttk.Button(btn_frame, text="Zoom In (+)", command=self.zoom_in_btn).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Zoom Out (-)", command=self.zoom_out_btn).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Reset View", command=self.reset_view).pack(side=tk.LEFT, padx=2)
        ttk.Label(frame_view, text="• Scroll Wheel to Zoom\n• Click & Drag Background to Pan\n• Interactive Legend (Bottom Left)\n• Minimap (Bottom Right) to Navigate", font=("Segoe UI", 8, "italic")).pack(padx=5, pady=2)

        # CONSOLE
        ttk.Label(self.left_panel, text="System Log:", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, padx=10, pady=(5, 0))
        self.console = tk.Text(self.left_panel, height=8, bg="#1e1e1e", fg="#00e676", font=("Consolas", 9), wrap=tk.WORD, borderwidth=0)
        self.console.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.log_sys("OSLC Environment Initialized.")

        # CANVAS & MINIMAP
        self.canvas = tk.Canvas(self.canvas_panel, bg="#ffffff", highlightthickness=1, highlightbackground="#cfd8dc")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.minimap = tk.Canvas(self.canvas_panel, width=200, height=150, bg="#eceff1", highlightthickness=1, highlightbackground="#90a4ae")
        self.minimap.place(relx=1.0, rely=1.0, anchor="se", x=-20, y=-20)
        self.minimap.bind("<Button-1>", self.on_minimap_click)
        self.minimap.bind("<B1-Motion>", self.on_minimap_click)

    def log_sys(self, message: str):
        self.console.config(state=tk.NORMAL)
        self.console.insert(tk.END, f"> {message}\n\n")
        self.console.see(tk.END)
        self.console.config(state=tk.DISABLED)

    # ==========================================
    # FILE OPERATIONS (SAVE / LOAD)
    # ==========================================
    def save_state(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON Files", "*.json")])
        if not file_path: return
        
        try:
            data = {
                "visibility": self.visibility,
                "tools": [{"name": t.name, "x": t.x, "y": t.y, "w": t.width, "h": t.height, "horizontal": t.display_horizontal, "icon_path": t.icon_path} for t in self.tools],
                "concepts": [{"id": c.id, "name": c.name, "tool": c.tool.name} for t in self.tools for c in t.concepts],
                "versions": [{"id": v.id, "concept": v.concept.id, "version_str": v.version_str, 
                              "pred": v.predecessor.id if v.predecessor else None, "links": [l.id for l in v.links]} 
                             for t in self.tools for c in t.concepts for v in c.versions],
                "local_configs": [{"id": c.id, "name": c.name, "type": c.config_type, "tool": c.tool.name, 
                                   "derived_from": c.derived_from.id if c.derived_from else None,
                                   "offset_x": c.offset_x, "offset_y": c.offset_y, "w": c.width, "h": c.height,
                                   "selections": {k: v.id for k, v in c.selections.items()}} 
                                  for t in self.tools for c in t.configs],
                "global_configs": [{"name": g.name, "type": g.config_type, "id": g.id, "x": g.x, "y": g.y, "w": g.width, "h": g.height,
                                    "derived_from": g.derived_from.id if g.derived_from else None, 
                                    "linked": {k: v.id for k, v in g.linked_configs.items()}} 
                                   for g in self.global_configs],
                "active_gc": self.active_gc.id if self.active_gc else None
            }
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
            self.log_sys("Configuration saved successfully.")
        except Exception as e:
            messagebox.showerror("Error Saving File", f"An error occurred:\n{e}")

    def load_state(self):
        file_path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
        if not file_path: return
        
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            self.tools.clear()
            self.global_configs.clear()
            self.active_gc = None
            self.link_source_artifact = None
            self.link_pull_target_conf = None
            if "visibility" in data:
                self.visibility.update(data["visibility"])
            self.reset_view()
            
            tool_map = {}
            concept_map = {}
            version_map = {}
            config_map = {}
            gc_map = {}
            
            for t_data in data.get("tools", []):
                t = Tool(t_data["name"])
                t.x, t.y, t.width, t.height = t_data["x"], t_data["y"], t_data["w"], t_data["h"]
                t.display_horizontal = t_data.get("horizontal", False)
                t.icon_path = t_data.get("icon_path")
                if t.icon_path and os.path.exists(t.icon_path):
                    try:
                        t.icon_image = tk.PhotoImage(file=t.icon_path)
                    except:
                        t.icon_image = None
                self.tools.append(t)
                tool_map[t.name] = t

            for c_data in data.get("concepts", []):
                tool = tool_map[c_data["tool"]]
                con = ArtifactConcept(c_data["name"], tool)
                con.id = c_data["id"]
                tool.concepts.append(con)
                concept_map[con.id] = con
                
            for v_data in data.get("versions", []):
                con = concept_map[v_data["concept"]]
                v = ArtifactVersion(con, v_data["version_str"])
                v.id = v_data["id"]
                con.versions.append(v)
                version_map[v.id] = v

            for v_data in data.get("versions", []):
                v = version_map[v_data["id"]]
                if v_data["pred"]: v.predecessor = version_map[v_data["pred"]]
                for l_id in v_data.get("links", []):
                    if l_id in version_map: v.links.append(version_map[l_id])

            for c_data in data.get("local_configs", []):
                tool = tool_map[c_data["tool"]]
                c = LocalConfig(c_data["name"], c_data["type"], tool)
                c.id = c_data["id"]
                c.offset_x = c_data.get("offset_x", 0.0)
                c.offset_y = c_data.get("offset_y", 0.0)
                c.width = c_data.get("w", 200.0)
                c.height = c_data.get("h", 80.0)
                
                for k, v_id in c_data.get("selections", {}).items():
                    if v_id in version_map:
                        c.selections[k] = version_map[v_id]
                        
                tool.configs.append(c)
                config_map[c.id] = c
                
            for c_data in data.get("local_configs", []):
                if c_data["derived_from"]:
                    config_map[c_data["id"]].derived_from = config_map.get(c_data["derived_from"])
                        
            for g_data in data.get("global_configs", []):
                g = GlobalConfig(g_data["name"], g_data["type"])
                g.id = g_data.get("id", g.id)
                g.x = g_data.get("x", 0.0)
                g.y = g_data.get("y", 0.0)
                g.width = g_data.get("w", 140.0)
                g.height = g_data.get("h", 65.0)
                self.global_configs.append(g)
                gc_map[g.id] = g
                
            for g_data in data.get("global_configs", []):
                g = gc_map[g_data["id"]]
                if g_data["derived_from"]:
                    g.derived_from = gc_map.get(g_data["derived_from"])
                for t_name, c_id in g_data.get("linked", {}).items():
                    if c_id in config_map:
                        g.linked_configs[t_name] = config_map[c_id]
                        
            active_gc_id = data.get("active_gc")
            if active_gc_id in gc_map:
                self.active_gc = gc_map[active_gc_id]
                
            self._update_gc_dropdown()
            if self.active_gc:
                self.gc_combobox.set(f"{self.active_gc.name} ({self.active_gc.config_type})")
            else:
                self.gc_combobox.set("None")
                
            self.log_sys("Configuration loaded successfully.")
            self.layout_needs_init = False 
            self.redraw_canvas()
            
        except Exception as e:
            messagebox.showerror("Error Loading File", f"An error occurred:\n{e}")

    # ==========================================
    # DELETION LOGIC (Cascade Cleanups)
    # ==========================================

    def _remove_artifact_from_config(self, conf: LocalConfig, version: ArtifactVersion):
        if version.concept.id in conf.selections:
            del conf.selections[version.concept.id]
            self.log_sys(f"Removed '{version.name}' from Configuration '{conf.name}'.")
            self.redraw_canvas()

    def _delete_concept_globally(self, concept: ArtifactConcept):
        if messagebox.askyesno("Confirm Global Delete", f"Permanently delete concept '{concept.name}' and ALL its versions globally?\nThis removes it from all Streams and Baselines."):
            # 1. Remove from all config selections
            for t in self.tools:
                for c in t.configs:
                    if concept.id in c.selections:
                        del c.selections[concept.id]
                    # 2. Erase external links pointing to any version of this concept
                    for art in c.artifacts:
                        art.links = [l for l in art.links if l.concept != concept]
                        
            # 3. Remove from tool
            if concept in concept.tool.concepts:
                concept.tool.concepts.remove(concept)
                
            if self.link_source_artifact and self.link_source_artifact.concept == concept:
                self.link_source_artifact = None
                
            self.log_sys(f"Concept '{concept.name}' completely eradicated.")
            self.redraw_canvas()

    def _delete_local_config(self, conf: LocalConfig):
        if messagebox.askyesno("Confirm Delete", f"Delete Configuration '{conf.name}'?\nThis removes the context, but the underlying Artifact Concepts remain in the Tool."):
            tool = conf.tool
            for gc in self.global_configs:
                keys_to_delete = [k for k, v in gc.linked_configs.items() if v == conf]
                for k in keys_to_delete:
                    del gc.linked_configs[k]
                    
            for t in self.tools:
                for c in t.configs:
                    if c.derived_from == conf:
                        c.derived_from = None
                        
            if conf.id in self.active_gc_link_coords:
                del self.active_gc_link_coords[conf.id]
                
            if conf in conf.tool.configs:
                conf.tool.configs.remove(conf)

            self.log_sys(f"Local Configuration '{conf.name}' deleted.")
            self.layout_tool(tool)
            self.redraw_canvas()

    def _delete_tool(self, tool: Tool):
        if messagebox.askyesno("Confirm Delete", f"Delete entire Tool '{tool.name}'?\nThis will permanently erase all its Streams, Baselines, and Concepts."):
            for conf in list(tool.configs):
                for gc in self.global_configs:
                    keys_to_delete = [k for k, v in gc.linked_configs.items() if v == conf]
                    for k in keys_to_delete: del gc.linked_configs[k]
            for c in list(tool.concepts):
                for t in self.tools:
                    for conf in t.configs:
                        for art in conf.artifacts:
                            art.links = [l for l in art.links if l.concept != c]
            if tool in self.tools:
                self.tools.remove(tool)
            self.log_sys(f"Tool '{tool.name}' completely deleted.")
            self.arrange_tools()

    def _delete_global_config(self, gc: GlobalConfig):
        if messagebox.askyesno("Confirm Delete", f"Delete Global Configuration '{gc.name}'?"):
            if self.active_gc == gc:
                self.active_gc = None
                self.gc_combobox.set("None")
                
            for other in self.global_configs:
                if other.derived_from == gc:
                    other.derived_from = None
                    
            if gc in self.global_configs:
                self.global_configs.remove(gc)
                
            self.log_sys(f"Global Configuration '{gc.name}' completely deleted.")
            self._update_gc_dropdown()
            self.redraw_canvas()

    # ==========================================
    # DOMAIN BUSINESS LOGIC & LAYOUT ENGINE
    # ==========================================

    def create_tool(self):
        name = simpledialog.askstring("New Tool", "Enter Contributor Tool Name:", parent=self.root)
        if name:
            new_tool = Tool(name)
            max_y = 250
            for t in self.tools:
                max_y = max(max_y, t.y + t.height + 20)
                
            new_tool.x = 50
            new_tool.y = max_y
            self.tools.append(new_tool)
            self.log_sys(f"Tool provisioned: '{name}'")
            self.redraw_canvas()

    def layout_tool(self, tool: Tool):
        if not tool.configs: return
            
        visible_configs = [c for c in tool.configs if self.visibility.get(c.config_type, True)]
        
        for c in tool.configs:
            min_h = max(60, 45 + len(c.artifacts) * 35)
            c.width = max(getattr(c, 'width', 200.0), 200.0)
            c.height = max(getattr(c, 'height', min_h), min_h)

        if tool.display_horizontal:
            children_map = {c: [] for c in visible_configs}
            for c in visible_configs:
                if c.derived_from and c.derived_from in visible_configs:
                    children_map[c.derived_from].append(c)
                    
            roots = [c for c in visible_configs if not c.derived_from or c.derived_from not in visible_configs]
            col_row_map = {}
            current_row = 0
            max_col = 0
            
            def dfs(node, col):
                nonlocal current_row, max_col
                max_col = max(max_col, col)
                col_row_map[node] = (col, current_row)
                if not children_map[node]:
                    current_row += 1
                else:
                    for child in children_map[node]: dfs(child, col + 1)
                    
            for root in roots: dfs(root, 0)
            
            row_heights = {}
            for c, (col, row) in col_row_map.items():
                row_heights[row] = max(row_heights.get(row, 0), c.height)
                
            col_widths = {}
            for c, (col, row) in col_row_map.items():
                col_widths[col] = max(col_widths.get(col, 200), c.width)

            for c, (col, row) in col_row_map.items():
                x_off = 20
                for i in range(col): x_off += col_widths.get(i, 200) + 40
                c.offset_x = x_off + (c.width / 2)
                
                y_offset = 50
                for r in range(row): y_offset += row_heights.get(r, 0) + 20
                c.offset_y = y_offset + (c.height / 2)
        else:
            conf_y = 50
            for config in visible_configs:
                config.offset_x = tool.width / 2
                config.offset_y = conf_y + config.height / 2
                conf_y += config.height + 15

    def arrange_tools(self):
        L_WIDTH = 2500
        gc_x = 50
        gc_y = 50
        max_h_row = 0
        for gc in self.global_configs:
            gc.width = max(140, len(gc.linked_configs) * 45 + 20)
            if gc_x + gc.width > L_WIDTH and gc_x > 50:
                gc_x = 50
                gc_y += max_h_row + 30
                max_h_row = 0
            gc.x = gc_x
            gc.y = gc_y
            max_h_row = max(max_h_row, gc.height)
            gc_x += gc.width + 30
            
        agg_bottom = gc_y + max_h_row + 80 if self.global_configs else 150

        total_tools = len(self.tools)
        if total_tools == 0: return
        
        for tool in self.tools:
            self.layout_tool(tool)
            max_w, max_h = 260, 150
            for config in tool.configs:
                if not self.visibility.get(config.config_type, True): continue
                max_w = max(max_w, config.offset_x + config.width/2 + 20)
                max_h = max(max_h, config.offset_y + config.height/2 + 20)
            tool.width = max_w
            tool.height = max_h
                
        x_offset = 50
        y_offset = agg_bottom
        max_h_in_row = 0
        
        for tool in self.tools:
            if x_offset + tool.width > L_WIDTH - 50 and x_offset > 50:
                x_offset = 50
                y_offset += max_h_in_row + 40
                max_h_in_row = 0
                
            tool.x = x_offset
            tool.y = y_offset
            max_h_in_row = max(max_h_in_row, tool.height)
            x_offset += tool.width + 30
        
        self.redraw_canvas()

    def create_local_config(self, config_type: str, target_tool: Optional[Tool] = None):
        if not self.tools: return messagebox.showwarning("Prerequisite Missing", "Provision a Domain Tool first.")
        
        tool = target_tool
        if not tool:
            tool_names = [t.name for t in self.tools]
            tool_name = self._ask_choice("Select Tool", "Target Tool for new configuration:", tool_names)
            if not tool_name: return
            tool = next(t for t in self.tools if t.name == tool_name)
            
        derived_from = None
        if config_type == 'Stream':
            local_baselines = [c for c in tool.configs if c.config_type == 'Baseline']
            if local_baselines:
                options = ["None (Start Fresh)"] + [c.name for c in local_baselines]
                base_choice = self._ask_choice("Branch Origin (Optional)", "Select a baseline to branch from, or start fresh:", options)
                if base_choice is None: return 
                if base_choice != "None (Start Fresh)":
                    derived_from = next(c for c in local_baselines if c.name == base_choice)

        conf_name = simpledialog.askstring(f"New {config_type}", f"Enter {config_type} identifier (e.g., main):", parent=self.root)
        if conf_name:
            new_conf = tool.add_config(conf_name, config_type, derived_from=derived_from)
            if derived_from:
                # OSLC Architecture: Just copy the pointers (selections)
                new_conf.selections = dict(derived_from.selections)
                self.log_sys(f"Local {config_type} '{conf_name}' branched from '{derived_from.name}'.")
            else:
                self.log_sys(f"Local {config_type} created: '{conf_name}'.")
            
            self.layout_tool(tool)
            self.redraw_canvas()

    def snap_local_baseline(self, source_conf: Optional[LocalConfig] = None):
        if not source_conf:
            local_streams = [c.id for t in self.tools for c in t.configs if c.config_type == 'Stream']
            if not local_streams: return messagebox.showwarning("Validation Error", "No local streams to baseline.")
            conf_id = self._ask_choice("Snap Local Baseline", "Select source Local Stream:", local_streams)
            if not conf_id: return
            source_conf = next(c for t in self.tools for c in t.configs if c.id == conf_id)
            
        new_name = simpledialog.askstring("Baseline Identifier", f"Enter name for new baseline off '{source_conf.name}':", parent=self.root)
        if new_name:
            new_conf = source_conf.tool.add_config(new_name, 'Baseline', derived_from=source_conf)
            # Copy active selection pointers over
            new_conf.selections = dict(source_conf.selections)
            self.log_sys(f"Local Baseline '{new_name}' snapped from '{source_conf.name}'.")
            
            self.layout_tool(source_conf.tool)
            self.redraw_canvas()

    def branch_local_config(self, source_conf: Optional[LocalConfig] = None):
        if not source_conf:
            local_baselines = [c.id for t in self.tools for c in t.configs if c.config_type == 'Baseline']
            if not local_baselines: return messagebox.showwarning("Validation Error", "No local baselines to branch from.")
            conf_id = self._ask_choice("Branch Local Config", "Select source Local Baseline:", local_baselines)
            if not conf_id: return
            source_conf = next(c for t in self.tools for c in t.configs if c.id == conf_id)
            
        new_name = simpledialog.askstring("Branch Identifier", f"Enter name for new stream off '{source_conf.name}':", parent=self.root)
        if new_name:
            new_conf = source_conf.tool.add_config(new_name, 'Stream', derived_from=source_conf)
            new_conf.selections = dict(source_conf.selections)
            self.log_sys(f"Local Stream '{new_name}' branched from '{source_conf.name}'.")
            
            self.layout_tool(source_conf.tool)
            self.redraw_canvas()

    def create_artifact(self, target_conf: Optional[LocalConfig] = None):
        if not self.tools: return messagebox.showwarning("Prerequisite Missing", "Provision a Domain Tool first.")
        
        conf = target_conf
        if not conf:
            streams = [c for t in self.tools for c in t.configs if c.config_type == 'Stream']
            if not streams: return messagebox.showwarning("Validation Error", "No local streams available.")
            options = [f"[{c.tool.name}] {c.name}" for c in streams]
            choice = self._ask_choice("Select Target Stream", "Select Stream to house new Concept:", options)
            if not choice: return
            conf = next(c for t in self.tools for c in t.configs if f"[{c.tool.name}] {c.name}" == choice)
            
        art_name = simpledialog.askstring("New Artifact Concept", "Enter Concept Name (e.g., REQ-101):", parent=self.root)
        if art_name:
            # Clean off any user-provided (v...) so we manage the concept cleanly
            art_name = re.sub(r"\s*\(v.*?\)$", "", art_name)
            concept = ArtifactConcept(art_name, conf.tool)
            conf.tool.concepts.append(concept)
            version = ArtifactVersion(concept, "v1.0")
            concept.versions.append(version)
            
            # Map the concept to this version in the config
            conf.selections[concept.id] = version
            self.log_sys(f"New Concept '{concept.name}' initialized at v1.0 in Stream '{conf.name}'.")
            self.redraw_canvas()

    def _create_new_version(self, old_v: ArtifactVersion, conf: LocalConfig):
        concept = old_v.concept
        children = [v for v in concept.versions if v.predecessor == old_v]
        
        if not children:
            try:
                base_str = old_v.version_str.replace('v', '')
                base = float(base_str) if '.' in base_str else int(base_str)
                new_v_str = f"v{math.floor(base) + 1}.0"
            except:
                new_v_str = f"{old_v.version_str}.1"
        else:
            # Branching the artifact tree
            new_v_str = f"{old_v.version_str}.{len(children) + 1}"
            
        new_v = ArtifactVersion(concept, new_v_str, predecessor=old_v)
        new_v.links = list(old_v.links)
        concept.versions.append(new_v)
        
        # Advance the pointer in the stream
        conf.selections[concept.id] = new_v
        
        # Auto-forward incoming links (Playground convenience feature)
        for t in self.tools:
            for c in t.configs:
                for a in c.artifacts:
                    if old_v in a.links and new_v not in a.links:
                        a.links.append(new_v)
                        
        self.log_sys(f"Concept '{concept.name}' advanced to {new_v_str} in Stream '{conf.name}'.")
        self.layout_tool(conf.tool)
        self.redraw_canvas()

    def _switch_version(self, conf: LocalConfig, concept: ArtifactConcept):
        options = [v.version_str for v in concept.versions]
        choice = self._ask_choice("Switch Artifact Version", f"Select context version for {concept.name}:", options)
        if choice:
            target_v = next(v for v in concept.versions if v.version_str == choice)
            conf.selections[concept.id] = target_v
            self.log_sys(f"Context shifted: '{concept.name}' is now at {target_v.version_str} in '{conf.name}'.")
            self.redraw_canvas()

    def create_global_config(self, config_type: str):
        name = simpledialog.askstring(f"New GC {config_type}", f"Enter Global {config_type} Name (e.g., Release 1.0):", parent=self.root)
        if name:
            gc = GlobalConfig(name, config_type)
            max_y = 50
            for g in self.global_configs:
                max_y = max(max_y, g.y + g.height + 30)
            gc.x = 50
            gc.y = max_y
            self.global_configs.append(gc)
            self._update_gc_dropdown()
            self.log_sys(f"Global {config_type} initialized: '{name}'")
            self.redraw_canvas()

    def link_to_gc(self):
        streams = [g.name for g in self.global_configs if g.config_type == 'Stream']
        if not streams: return messagebox.showwarning("Prerequisite Missing", "Create a Global Configuration Stream first.")

        gc_name = self._ask_choice("Select Target GC", "Select the GC Stream to modify:", streams)
        if not gc_name: return
        gc = next(g for g in self.global_configs if g.name == gc_name)

        all_configs = [c.id for t in self.tools for c in t.configs]
        if not all_configs: return messagebox.showwarning("Prerequisite Missing", "No local configurations exist across any tools.")

        conf_id = self._ask_choice("Select Payload", f"Select Local Config to add to [{gc.name}]:", all_configs)
        if not conf_id: return
        selected_conf = next((c for t in self.tools for c in t.configs if c.id == conf_id), None)
        
        if selected_conf:
            gc.linked_configs[selected_conf.tool.name] = selected_conf
            self.log_sys(f"OSLC Link Established: GC '{gc.name}' -> '{selected_conf.id}'")
            self.redraw_canvas()

    def snap_gc_baseline(self, source_gc: Optional[GlobalConfig] = None):
        if not source_gc:
            streams = [g.name for g in self.global_configs if g.config_type == 'Stream']
            if not streams: return messagebox.showwarning("Validation Error", "No GC Streams available to baseline.")
            gc_name = self._ask_choice("Baseline Origin", "Select source GC Stream:", streams)
            if not gc_name: return
            source_gc = next(g for g in self.global_configs if g.name == gc_name)

        new_name = simpledialog.askstring("Baseline Identifier", "Enter name for the new GC Baseline:", parent=self.root)
        if new_name:
            new_gc = GlobalConfig(new_name, 'Baseline')
            new_gc.x = source_gc.x + 50
            new_gc.y = source_gc.y + source_gc.height + 30
            new_gc.derived_from = source_gc
            new_gc.linked_configs = source_gc.linked_configs.copy()
            self.global_configs.append(new_gc)
            self._update_gc_dropdown()
            self.log_sys(f"Snapshot Created: GC Baseline '{new_name}' generated from '{source_gc.name}'.")
            self.redraw_canvas()

    def branch_gc(self, source_gc: Optional[GlobalConfig] = None):
        if not source_gc:
            baselines = [g.name for g in self.global_configs if g.config_type == 'Baseline']
            if not baselines: return messagebox.showwarning("Validation Error", "No GC Baselines available to branch.")
            gc_name = self._ask_choice("Branch Origin", "Select source GC Baseline:", baselines)
            if not gc_name: return
            source_gc = next(g for g in self.global_configs if g.name == gc_name)

        new_name = simpledialog.askstring("Branch Identifier", "Enter name for the new GC Stream (Branch):", parent=self.root)
        if new_name:
            new_gc = GlobalConfig(new_name, 'Stream')
            new_gc.x = source_gc.x + 50
            new_gc.y = source_gc.y + source_gc.height + 30
            new_gc.derived_from = source_gc
            new_gc.linked_configs = source_gc.linked_configs.copy()
            self.global_configs.append(new_gc)
            self._update_gc_dropdown()
            self.log_sys(f"Branch Created: GC Stream '{new_name}' forked from '{source_gc.name}'.")
            self.redraw_canvas()

    def _update_gc_dropdown(self):
        values = ["None"] + [f"{g.name} ({g.config_type})" for g in self.global_configs]
        self.gc_combobox['values'] = values

    def change_context(self, event=None):
        selection = self.gc_combobox.get()
        if selection == "None":
            self.active_gc = None
            self.log_sys("Global Context cleared.")
        else:
            clean_name = selection.rsplit(" (", 1)[0]
            self.active_gc = next((g for g in self.global_configs if g.name == clean_name), None)
            self.log_sys(f"Global Context set to '{clean_name}'.")
        self.redraw_canvas()

    def _ask_choice(self, title: str, prompt: str, options: List[str]) -> Optional[str]:
        if not options: return None
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        root_x, root_y = self.root.winfo_rootx(), self.root.winfo_rooty()
        root_width, root_height = self.root.winfo_width(), self.root.winfo_height()
        dialog.geometry(f"400x150+{root_x + root_width//2 - 200}+{root_y + root_height//2 - 75}")

        result = [None]
        ttk.Label(dialog, text=prompt, wraplength=380, font=("Segoe UI", 10)).pack(pady=10, padx=10, anchor=tk.W)

        var = tk.StringVar()
        var.set(options[0])
        ttk.Combobox(dialog, textvariable=var, values=options, state="readonly", width=50).pack(padx=10, pady=5)

        def on_ok():
            result[0] = var.get()
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="OK", command=on_ok).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="Cancel", command=lambda: dialog.destroy()).pack(side=tk.LEFT, padx=10)

        self.root.wait_window(dialog)
        return result[0]

    # ==========================================
    # RENAMING & ASSET HELPERS
    # ==========================================

    def _rename_tool(self, tool: Tool):
        new_name = simpledialog.askstring("Rename Tool", f"New name for '{tool.name}':", initialvalue=tool.name, parent=self.root)
        if new_name:
            tool.name = new_name
            self.log_sys(f"Tool renamed to '{new_name}'.")
            self.redraw_canvas()

    def _set_tool_icon(self, tool: Tool):
        file_path = filedialog.askopenfilename(filetypes=[("GIF Files", "*.gif")])
        if file_path:
            try:
                tool.icon_path = file_path
                tool.icon_image = tk.PhotoImage(file=file_path)
                self.log_sys(f"Icon updated for Tool '{tool.name}'.")
                self.redraw_canvas()
            except Exception as e:
                messagebox.showerror("Icon Error", f"Could not load GIF:\n{e}")

    def _rename_local_config(self, conf: LocalConfig):
        if conf.config_type == 'Baseline':
            return messagebox.showwarning("Immutable Object", "Baselines cannot be renamed.")
        new_name = simpledialog.askstring(f"Rename {conf.config_type}", f"New name for '{conf.name}':", initialvalue=conf.name, parent=self.root)
        if new_name:
            conf.name = new_name
            self.log_sys(f"Local {conf.config_type} renamed to '{new_name}'.")
            self.redraw_canvas()

    def _rename_global_config(self, gc: GlobalConfig):
        if gc.config_type == 'Baseline':
            return messagebox.showwarning("Immutable Object", "Baselines cannot be renamed.")
        new_name = simpledialog.askstring(f"Rename GC {gc.config_type}", f"New name for '{gc.name}':", initialvalue=gc.name, parent=self.root)
        if new_name:
            gc.name = new_name
            self.log_sys(f"Global {gc.config_type} renamed to '{new_name}'.")
            self._update_gc_dropdown()
            self.redraw_canvas()

    def _rename_concept(self, concept: ArtifactConcept):
        new_name = simpledialog.askstring("Rename Concept", f"New identifier for concept '{concept.name}':", initialvalue=concept.name, parent=self.root)
        if new_name:
            old_name = concept.name
            concept.name = new_name
            self.log_sys(f"Artifact Concept '{old_name}' renamed globally to '{new_name}'.")
            self.redraw_canvas()

    # ==========================================
    # INTERACTION: ZOOM, PAN, DRAG & CLICK
    # ==========================================

    def zoom_in_btn(self):
        self.zoom *= 1.2
        self.redraw_canvas()

    def zoom_out_btn(self):
        self.zoom /= 1.2
        self.redraw_canvas()

    def reset_view(self):
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.redraw_canvas()

    def on_mouse_wheel(self, event):
        scale = 1.1 if (event.num == 4 or event.delta > 0) else 1/1.1
        self.pan_x = event.x - (event.x - self.pan_x) * scale
        self.pan_y = event.y - (event.y - self.pan_y) * scale
        self.zoom *= scale
        self.redraw_canvas()

    def on_canvas_press(self, event):
        clicked_items = self.canvas.find_withtag("current")
        tags = self.canvas.gettags(clicked_items[0]) if clicked_items else ()
        
        # 1. Legend Toggles
        cb_tag = next((t for t in tags if t.startswith("LEGEND_CB::")), None)
        if cb_tag:
            key = cb_tag.split("::")[1]
            self.visibility[key] = not self.visibility[key]
            self.redraw_canvas()
            return

        # 2. Link Pull Interception
        if getattr(self, 'link_pull_target_conf', None) is not None:
            conf_tag = next((t for t in tags if t.startswith("CONF_DRAG::")), None)
            if conf_tag:
                conf_id = conf_tag.split("::", 1)[1]
                clicked_conf = next((c for t in self.tools for c in t.configs if c.id == conf_id), None)
                if clicked_conf and clicked_conf != self.link_pull_target_conf:
                    self._execute_link_pull(self.link_pull_target_conf, clicked_conf)
                else:
                    self.log_sys("Link transfer cancelled.")
            else:
                self.log_sys("Link transfer cancelled.")
            self.link_pull_target_conf = None
            self.redraw_canvas()
            return
        
        # 3. Background Panning
        if not tags or "zone" in tags:
            if self.link_source_artifact:
                self.link_source_artifact = None
                self.log_sys("Link creation cancelled.")
                self.redraw_canvas()
                return
            self.is_panning = True
            self.drag_start_x = event.x
            self.drag_start_y = event.y
            self.orig_pan_x = self.pan_x
            self.orig_pan_y = self.pan_y
            return
            
        # 4. Tool Header Toggles
        tool_toggle_tag = next((t for t in tags if t.startswith("TOOL_TOGGLE::")), None)
        if tool_toggle_tag:
            tool_name = tool_toggle_tag.split("::", 1)[1]
            tool = next((t for t in self.tools if t.name == tool_name), None)
            if tool:
                tool.display_horizontal = not tool.display_horizontal
                tool.width = 260
                tool.height = 150
                self.arrange_tools()
                return

        # 5. Tool Gear Menu
        tool_gear_tag = next((t for t in tags if t.startswith("TOOL_GEAR::")), None)
        if tool_gear_tag:
            tool_name = tool_gear_tag.split("::", 1)[1]
            tool = next((t for t in self.tools if t.name == tool_name), None)
            if tool:
                menu = tk.Menu(self.root, tearoff=0, font=("Segoe UI", 9))
                menu.add_command(label="✏️ Rename Tool", command=lambda: self._rename_tool(tool))
                menu.add_command(label="🖼️ Set Tool Symbol (.gif)", command=lambda: self._set_tool_icon(tool))
                menu.add_separator()
                menu.add_command(label="🌱 Add Stream to Tool", command=lambda: self.create_local_config('Stream', tool))
                menu.add_separator()
                menu.add_command(label="❌ Delete Tool", command=lambda: self._delete_tool(tool))
                menu.tk_popup(event.x_root, event.y_root)
                return
                
        # 6. Global Config Gear Menu
        gc_gear_tag = next((t for t in tags if t.startswith("GC_GEAR::")), None)
        if gc_gear_tag:
            gc_id = gc_gear_tag.split("::", 1)[1]
            clicked_gc = next((g for g in self.global_configs if g.id == gc_id), None)
            if clicked_gc:
                menu = tk.Menu(self.root, tearoff=0, font=("Segoe UI", 9))
                if clicked_gc.config_type == 'Stream':
                    menu.add_command(label="✏️ Rename Global Stream", command=lambda: self._rename_global_config(clicked_gc))
                    menu.add_command(label="📸 Snap GC Baseline", command=lambda: self.snap_gc_baseline(clicked_gc))
                menu.add_command(label="🌿 Branch GC", command=lambda: self.branch_gc(clicked_gc))
                menu.add_separator()
                menu.add_command(label="❌ Delete Global Config", command=lambda: self._delete_global_config(clicked_gc))
                menu.tk_popup(event.x_root, event.y_root)
                return

        # 7. Local Config Gear Menu
        conf_gear_tag = next((t for t in tags if t.startswith("CONF_GEAR::")), None)
        if conf_gear_tag:
            conf_id = conf_gear_tag.split("::", 1)[1]
            clicked_conf = next((c for t in self.tools for c in t.configs if c.id == conf_id), None)
            if clicked_conf:
                menu = tk.Menu(self.root, tearoff=0, font=("Segoe UI", 9))
                if clicked_conf.config_type == 'Stream':
                    menu.add_command(label="✏️ Rename Stream", command=lambda: self._rename_local_config(clicked_conf))
                    menu.add_command(label="📸 Snap Local Baseline", command=lambda: self.snap_local_baseline(clicked_conf))
                    menu.add_command(label="📄 Create Artifact Concept", command=lambda: self.create_artifact(clicked_conf))
                menu.add_command(label="🌿 Branch Local Config", command=lambda: self.branch_local_config(clicked_conf))
                menu.add_separator()
                menu.add_command(label="📥 Pull Links FROM...", command=lambda: self._start_link_pull(clicked_conf))
                menu.add_separator()
                menu.add_command(label="❌ Delete Configuration", command=lambda: self._delete_local_config(clicked_conf))
                menu.tk_popup(event.x_root, event.y_root)
                return

        # 8. Artifact Menus
        art_render_tag = next((t for t in tags if t.startswith("ART_RENDER||")), None)
        if art_render_tag:
            _, conf_id, art_id = art_render_tag.split("||")
            clicked_conf = next((c for t in self.tools for c in t.configs if c.id == conf_id), None)
            clicked_art = next((a for a in clicked_conf.artifacts if a.id == art_id), None) if clicked_conf else None
            if not clicked_art: return
            
            menu = tk.Menu(self.root, tearoff=0, font=("Segoe UI", 9))
            
            # Renaming & History
            menu.add_command(label="✏️ Rename Concept Globally", command=lambda: self._rename_concept(clicked_art.concept))
            menu.add_command(label="📜 View Version History", command=lambda: self._show_version_history(clicked_art))
            if clicked_conf.config_type == 'Stream':
                menu.add_command(label="🔄 Switch Version...", command=lambda: self._switch_version(clicked_conf, clicked_art.concept))
            menu.add_separator()
            
            # Linking
            if self.link_source_artifact is None:
                menu.add_command(label="🔗 Set as Link Source", command=lambda: self._set_link_source(clicked_art))
            else:
                if self.link_source_artifact != clicked_art:
                    menu.add_command(label=f"➡️ Bind Link from '{self.link_source_artifact.name}'", command=lambda: self._bind_link(clicked_art))
                menu.add_command(label="❌ Cancel Linking Mode", command=self._cancel_link)
            
            if clicked_art.links:
                link_menu = tk.Menu(menu, tearoff=0, font=("Segoe UI", 9))
                for target_art in clicked_art.links:
                    link_menu.add_command(label=f"Remove: {target_art.name}", command=lambda ta=target_art: self._remove_link(clicked_art, ta))
                menu.add_cascade(label="✂️ Remove Existing Link...", menu=link_menu)

            # Versioning
            if clicked_conf.config_type == 'Stream':
                menu.add_separator()
                menu.add_command(label="🌱 Generate New Version", command=lambda: self._create_new_version(clicked_art, clicked_conf))
                
            menu.add_separator()
            menu.add_command(label="❌ Remove from Stream", command=lambda: self._remove_artifact_from_config(clicked_conf, clicked_art))
            menu.add_command(label="🗑️ Delete Concept Globally", command=lambda: self._delete_concept_globally(clicked_art.concept))
            menu.tk_popup(event.x_root, event.y_root)
            return

        # 9. Local Config Resize
        conf_resize = next((t for t in tags if t.startswith("CONF_RESIZE::")), None)
        if conf_resize:
            conf_id = conf_resize.split("::", 1)[1]
            c = next((c for t in self.tools for c in t.configs if c.id == conf_id), None)
            if c:
                self.resizing_conf = c
                self.drag_start_x = event.x
                self.drag_start_y = event.y
                self.orig_conf_w = c.width
                self.orig_conf_h = c.height
                return

        # 10. Local Config Drag
        conf_drag = next((t for t in tags if t.startswith("CONF_DRAG::")), None)
        if conf_drag:
            conf_id = conf_drag.split("::", 1)[1]
            self.dragging_conf = next((c for t in self.tools for c in t.configs if c.id == conf_id), None)
            if self.dragging_conf:
                self.drag_start_x = event.x
                self.drag_start_y = event.y
                self.orig_conf_offset_x = self.dragging_conf.offset_x
                self.orig_conf_offset_y = self.dragging_conf.offset_y
                return 

        # 11. Global Config Resize
        gc_resize = next((t for t in tags if t.startswith("GC_RESIZE::")), None)
        if gc_resize:
            gc_id = gc_resize.split("::", 1)[1]
            gc = next((g for g in self.global_configs if g.id == gc_id), None)
            if gc:
                self.resizing_gc = gc
                self.drag_start_x = event.x
                self.drag_start_y = event.y
                self.orig_gc_w = gc.width
                self.orig_gc_h = gc.height
                return

        # 12. Global Config Drag
        gc_drag = next((t for t in tags if t.startswith("GC_DRAG::")), None)
        if gc_drag:
            gc_id = gc_drag.split("::", 1)[1]
            gc = next((g for g in self.global_configs if g.id == gc_id), None)
            if gc:
                self.dragging_gc = gc
                self.drag_start_x = event.x
                self.drag_start_y = event.y
                self.orig_gc_x = gc.x
                self.orig_gc_y = gc.y
                return
                
        # 13. Tool Resize
        tool_resize = next((t for t in tags if t.startswith("TOOL_RESIZE::")), None)
        if tool_resize:
            tool_name = tool_resize.split("::", 1)[1]
            tool = next((t for t in self.tools if t.name == tool_name), None)
            if tool:
                self.resizing_tool = tool
                self.drag_start_x = event.x
                self.drag_start_y = event.y
                self.orig_tool_w = tool.width
                self.orig_tool_h = tool.height
                return
                
        # 14. Tool Drag
        tool_drag = next((t for t in tags if t.startswith("TOOL_DRAG::")), None)
        if tool_drag:
            tool_name = tool_drag.split("::", 1)[1]
            tool = next((t for t in self.tools if t.name == tool_name), None)
            if tool:
                self.dragging_tool = tool
                self.drag_start_x = event.x
                self.drag_start_y = event.y
                self.orig_tool_x = tool.x
                self.orig_tool_y = tool.y
                return

    def on_canvas_drag(self, event):
        if self.is_panning:
            self.pan_x = self.orig_pan_x + (event.x - self.drag_start_x)
            self.pan_y = self.orig_pan_y + (event.y - self.drag_start_y)
            self.redraw_canvas()
        elif self.dragging_tool:
            dx = (event.x - self.drag_start_x) / self.zoom
            dy = (event.y - self.drag_start_y) / self.zoom
            self.dragging_tool.x = self.orig_tool_x + dx
            self.dragging_tool.y = self.orig_tool_y + dy
            self.redraw_canvas()
        elif self.resizing_tool:
            dx = (event.x - self.drag_start_x) / self.zoom
            dy = (event.y - self.drag_start_y) / self.zoom
            self.resizing_tool.width = max(200, self.orig_tool_w + dx)
            self.resizing_tool.height = max(150, self.orig_tool_h + dy)
            self.redraw_canvas()
        elif self.resizing_conf:
            dx = (event.x - self.drag_start_x) / self.zoom
            dy = (event.y - self.drag_start_y) / self.zoom
            self.resizing_conf.width = max(150, self.orig_conf_w + dx)
            self.resizing_conf.height = max(60, self.orig_conf_h + dy)
            self.redraw_canvas()
        elif self.dragging_conf:
            dx = (event.x - self.drag_start_x) / self.zoom
            dy = (event.y - self.drag_start_y) / self.zoom
            self.dragging_conf.offset_x = self.orig_conf_offset_x + dx
            self.dragging_conf.offset_y = self.orig_conf_offset_y + dy
            self.redraw_canvas()
        elif self.dragging_gc:
            dx = (event.x - self.drag_start_x) / self.zoom
            dy = (event.y - self.drag_start_y) / self.zoom
            self.dragging_gc.x = self.orig_gc_x + dx
            self.dragging_gc.y = self.orig_gc_y + dy
            self.redraw_canvas()
        elif self.resizing_gc:
            dx = (event.x - self.drag_start_x) / self.zoom
            dy = (event.y - self.drag_start_y) / self.zoom
            self.resizing_gc.width = max(140, self.orig_gc_w + dx)
            self.resizing_gc.height = max(65, self.orig_gc_h + dy)
            self.redraw_canvas()

    def on_canvas_release(self, event):
        self.is_panning = False
        self.dragging_tool = None
        self.resizing_tool = None
        self.dragging_conf = None
        self.resizing_conf = None
        self.dragging_gc = None
        self.resizing_gc = None
        
    def on_minimap_click(self, event):
        L_WIDTH, L_HEIGHT = self.get_logical_bounds()
        scale_x = 200 / max(1, L_WIDTH)
        scale_y = 150 / max(1, L_HEIGHT)

        logical_x = event.x / scale_x
        logical_y = event.y / scale_y

        self.pan_x = self.canvas.winfo_width()/2 - logical_x * self.zoom
        self.pan_y = self.canvas.winfo_height()/2 - logical_y * self.zoom
        self.redraw_canvas()

    # ==========================================
    # LOGICAL TRANSFORM ENGINE 
    # ==========================================
    
    def sx(self, x: float) -> float: return x * self.zoom + self.pan_x
    def sy(self, y: float) -> float: return y * self.zoom + self.pan_y
    def sz(self, size: float) -> float: return max(1, int(size * self.zoom))
    def sf(self, family: str, size: int, weight: str = "normal") -> tuple:
        return (family, max(6, int(size * self.zoom)), weight)

    def draw_rect(self, x1, y1, x2, y2, **kw):
        return self.canvas.create_rectangle(self.sx(x1), self.sy(y1), self.sx(x2), self.sy(y2), **kw)

    def draw_text(self, x, y, text, size, weight="normal", **kw):
        return self.canvas.create_text(self.sx(x), self.sy(y), text=text, font=self.sf("Segoe UI", size, weight), **kw)

    def draw_line(self, *coords, **kw):
        scaled = [self.sx(c) if i%2==0 else self.sy(c) for i, c in enumerate(coords)]
        if 'width' in kw: kw['width'] = max(1, int(kw['width'] * self.zoom))
        return self.canvas.create_line(*scaled, **kw)

    def draw_polygon(self, *coords, **kw):
        scaled = [self.sx(c) if i%2==0 else self.sy(c) for i, c in enumerate(coords)]
        return self.canvas.create_polygon(*scaled, **kw)

    def draw_image(self, x, y, img, **kw):
        return self.canvas.create_image(self.sx(x), self.sy(y), image=img, **kw)

    def get_logical_bounds(self):
        max_y = 2000
        max_x = 3000
        for tool in self.tools:
            max_y = max(max_y, tool.y + tool.height + 200)
            max_x = max(max_x, tool.x + tool.width + 200)
        for gc in self.global_configs:
            max_y = max(max_y, gc.y + gc.height + 200)
            max_x = max(max_x, gc.x + gc.width + 200)
        return max_x, max_y

    def update_minimap(self):
        self.minimap.delete("all")
        L_WIDTH, L_HEIGHT = self.get_logical_bounds()

        scale_x = 200 / L_WIDTH
        scale_y = 150 / L_HEIGHT

        self.minimap.create_rectangle(0, 0, 200, 150, fill="#eceff1", outline="")

        for gc in self.global_configs:
            mx1, my1 = gc.x * scale_x, gc.y * scale_y
            mx2, my2 = (gc.x + gc.width) * scale_x, (gc.y + gc.height) * scale_y
            self.minimap.create_rectangle(mx1, my1, mx2, my2, fill="#ff9800" if gc.config_type == 'Stream' else "#4caf50", outline="")

        for tool in self.tools:
            mx1, my1 = tool.x * scale_x, tool.y * scale_y
            mx2, my2 = (tool.x + tool.width) * scale_x, (tool.y + tool.height) * scale_y
            self.minimap.create_rectangle(mx1, my1, mx2, my2, fill="#b0bec5", outline="")

        vp_lx1 = (0 - self.pan_x) / self.zoom
        vp_ly1 = (0 - self.pan_y) / self.zoom
        vp_lx2 = (self.canvas.winfo_width() - self.pan_x) / self.zoom
        vp_ly2 = (self.canvas.winfo_height() - self.pan_y) / self.zoom

        self.minimap.create_rectangle(vp_lx1*scale_x, vp_ly1*scale_y, vp_lx2*scale_x, vp_ly2*scale_y, outline="red", width=2)

    # ==========================================
    # RENDER PIPELINE
    # ==========================================

    def _draw_config_box(self, config: LocalConfig, tool: Tool, cx: float, cy: float, is_active: bool):
        conf_width = config.width
        conf_height = config.height
        
        bg_color = "#fff3e0" if config.config_type == 'Stream' else "#e8f5e9"
        outline_color = "#d32f2f" if is_active else "#90a4ae"
        line_width = 3 if is_active else 1
        
        if getattr(self, 'link_pull_target_conf', None) == config:
            outline_color = "#9c27b0"  
            line_width = 3
        
        conf_tags = (f"CONF_DRAG::{config.id}",)
        self.draw_rect(cx - conf_width/2, cy - conf_height/2, cx + conf_width/2, cy + conf_height/2, 
                                     fill=bg_color, outline=outline_color, width=line_width, tags=conf_tags)
        self.draw_text(cx, cy - conf_height/2 + 15, f"{config.name} [{config.config_type[0]}]", 
                                9, "bold", fill="#263238", tags=conf_tags)
        
        gear_x = cx + conf_width/2 - 15
        gear_y = cy - conf_height/2 + 15
        gear_tags = (f"CONF_GEAR::{config.id}",)
        self.draw_rect(gear_x - 10, gear_y - 10, gear_x + 10, gear_y + 10, fill="#e0e0e0", outline="#9e9e9e", tags=gear_tags)
        self.draw_text(gear_x, gear_y, "⚙️", 10, "bold", fill="#424242", tags=gear_tags)
        
        resize_tags = (f"CONF_RESIZE::{config.id}",)
        self.draw_polygon(cx + conf_width/2 - 15, cy + conf_height/2,
                          cx + conf_width/2, cy + conf_height/2 - 15,
                          cx + conf_width/2, cy + conf_height/2,
                          fill="#90a4ae", tags=resize_tags)
                                
        art_y = cy - conf_height/2 + 45
        for art in config.artifacts:
            art.canvas_x = cx
            art.canvas_y = art_y
            
            # Store rendering coords contextually
            self.render_coords[(config.id, art.id)] = (art.canvas_x, art.canvas_y)
            
            art_width_half = min(100, (conf_width / 2) - 15)
            
            if art.predecessor is not None:
                self.draw_rect(art.canvas_x - art_width_half + 4, art.canvas_y - 12 + 4, 
                                             art.canvas_x + art_width_half + 4, art.canvas_y + 12 + 4, 
                                             fill="#cfd8dc", outline="#90a4ae")
                self.draw_rect(art.canvas_x - art_width_half + 2, art.canvas_y - 12 + 2, 
                                             art.canvas_x + art_width_half + 2, art.canvas_y + 12 + 2, 
                                             fill="#eceff1", outline="#b0bec5")
            
            is_source = (art == self.link_source_artifact)
            a_bg = "#bbdefb" if is_source else "#ffffff"
            a_out = "#1565c0" if is_source else "#64b5f6"
            a_wid = 2 if is_source else 1
            
            art_tags = (f"ART_RENDER||{config.id}||{art.id}",)
            self.draw_rect(art.canvas_x - art_width_half, art.canvas_y - 12, 
                                         art.canvas_x + art_width_half, art.canvas_y + 12, 
                                         fill=a_bg, outline=a_out, width=a_wid, tags=art_tags)
            self.draw_text(art.canvas_x, art.canvas_y, f"📄 {art.name}", 8, 
                                    fill="#0d47a1", tags=art_tags)
            art_y += 35

    def redraw_canvas(self, event=None):
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        
        if self.layout_needs_init and width > 100:
            self.layout_needs_init = False
            self.arrange_tools()
            return

        self.canvas.delete("all")
        if width <= 1 or height <= 1: return 
        
        self.active_gc_link_coords = {}
        self.render_coords = {} 
        
        # --- 1. Draw Aggregator Zone (Top) ---
        L_WIDTH = 3000
        agg_height = 150
        for gc in self.global_configs:
            agg_height = max(agg_height, gc.y + gc.height + 40)
            
        self.draw_rect(20, 20, L_WIDTH - 20, agg_height, fill="#f8fdff", outline="#90caf9", width=2, tags="zone")
        self.draw_text(L_WIDTH/2, 40, "OSLC Global Configuration Management (GCM Aggregator)", 14, "bold", fill="#1565c0", tags="zone")
        
        if self.global_configs:
            for gc in self.global_configs:
                min_w = max(140, len(gc.linked_configs) * 45 + 20)
                if gc.width < min_w: gc.width = min_w
                if gc.height < 65: gc.height = 65
                
                gc.canvas_x = gc.x + gc.width / 2
                gc.canvas_y = gc.y + gc.height / 2
                
                is_active = (gc == self.active_gc)
                bg_color = "#fff3e0" if gc.config_type == 'Stream' else "#e8f5e9"
                outline_color = "#d32f2f" if is_active else ("#ff9800" if gc.config_type == 'Stream' else "#4caf50")
                line_width = 3 if is_active else 1

                gc_tags = (f"GC_DRAG::{gc.id}",)
                
                self.draw_rect(gc.x + 3, gc.y + 3, gc.x + gc.width + 3, gc.y + gc.height + 3, fill="#cfd8dc", outline="")
                self.draw_rect(gc.x, gc.y, gc.x + gc.width, gc.y + gc.height, fill=bg_color, outline=outline_color, width=line_width, tags=gc_tags)
                self.draw_text(gc.canvas_x, gc.y + 15, gc.name, 10, "bold", fill="#263238", tags=gc_tags)
                self.draw_text(gc.canvas_x, gc.y + 28, f"[{gc.config_type}]", 8, fill="#546e7a", tags=gc_tags)
                
                self.draw_polygon(gc.x + gc.width - 15, gc.y + gc.height, gc.x + gc.width, gc.y + gc.height - 15,
                                  gc.x + gc.width, gc.y + gc.height, fill="#90a4ae", tags=(f"GC_RESIZE::{gc.id}",))
                                  
                gear_x = gc.x + gc.width - 15
                gear_y = gc.y + 15
                self.draw_rect(gear_x - 10, gear_y - 10, gear_x + 10, gear_y + 10, fill="#e0e0e0", outline="#9e9e9e", tags=(f"GC_GEAR::{gc.id}",))
                self.draw_text(gear_x, gear_y, "⚙️", 10, "bold", fill="#424242", tags=(f"GC_GEAR::{gc.id}",))
                
                if gc.linked_configs:
                    inner_x = gc.x + 10
                    iy = gc.y + 40
                    for tool_name, l_conf in gc.linked_configs.items():
                        if inner_x + 40 > gc.x + gc.width:
                            inner_x = gc.x + 10
                            iy += 25
                            
                        ix1, iy1 = inner_x, iy
                        ix2, iy2 = inner_x + 35, iy + 18
                        
                        i_bg = "#fff3e0" if l_conf.config_type == 'Stream' else "#e8f5e9"
                        i_out = "#ff9800" if l_conf.config_type == 'Stream' else "#4caf50"
                        
                        self.draw_rect(ix1, iy1, ix2, iy2, fill=i_bg, outline=i_out)
                        self.draw_text((ix1+ix2)/2, (iy1+iy2)/2, tool_name[:3].upper(), 7, "bold", fill="#263238")
                        
                        if is_active:
                            self.active_gc_link_coords[l_conf.id] = ((ix1+ix2)/2, iy2)
                            
                        inner_x += 45

        # --- 2. Draw Domain Tools Zone (Bottom) ---
        for tool in self.tools:
            self.draw_rect(tool.x, tool.y, tool.x + tool.width, tool.y + tool.height, fill="#fafafa", outline="#b0bec5", width=2)
            self.draw_rect(tool.x, tool.y, tool.x + tool.width, tool.y + 35, fill="#eceff1", outline="#b0bec5", width=2, tags=(f"TOOL_DRAG::{tool.name}",))
            
            # Draw Tool Icon/Symbol
            if tool.icon_image:
                self.draw_image(tool.x + 20, tool.y + 17, tool.icon_image, tags=(f"TOOL_DRAG::{tool.name}",))

            self.draw_text(tool.x + (tool.width/2), tool.y + 17, tool.name, 10, "bold", fill="#37474f", tags=(f"TOOL_DRAG::{tool.name}",))
            
            self.draw_polygon(tool.x + tool.width - 15, tool.y + tool.height, tool.x + tool.width, tool.y + tool.height - 15,
                                       tool.x + tool.width, tool.y + tool.height, fill="#90a4ae", tags=(f"TOOL_RESIZE::{tool.name}",))

            btn_x = tool.x + tool.width - 25
            btn_y = tool.y + 17
            icon = "↔" if not tool.display_horizontal else "↕"
            self.draw_rect(btn_x - 12, btn_y - 10, btn_x + 12, btn_y + 10, fill="#e0e0e0", outline="#9e9e9e", tags=(f"TOOL_TOGGLE::{tool.name}",))
            self.draw_text(btn_x, btn_y, icon, 12, "bold", fill="#424242", tags=(f"TOOL_TOGGLE::{tool.name}",))

            gear_x = btn_x - 30
            self.draw_rect(gear_x - 12, btn_y - 10, gear_x + 12, btn_y + 10, fill="#e0e0e0", outline="#9e9e9e", tags=(f"TOOL_GEAR::{tool.name}",))
            self.draw_text(gear_x, btn_y, "⚙️", 12, "bold", fill="#424242", tags=(f"TOOL_GEAR::{tool.name}",))

            for config in tool.configs:
                if not self.visibility.get(config.config_type, True): continue
                
                config.canvas_x = tool.x + config.offset_x
                config.canvas_y = tool.y + config.offset_y
                
                is_active = self.active_gc and config in self.active_gc.linked_configs.values()
                self._draw_config_box(config, tool, config.canvas_x, config.canvas_y, is_active)

        # --- 2.5 Draw Lineage Branches (Purple/Gray dashed) ---
        if self.visibility["Branch"]:
            for gc in self.global_configs:
                if gc.derived_from and gc.derived_from.canvas_x != 0:
                    self.draw_line(gc.derived_from.canvas_x, gc.derived_from.canvas_y + 25, 
                                            gc.canvas_x, gc.canvas_y - 25, fill="#9e9e9e", width=2, dash=(2, 4), arrow=tk.LAST, smooth=True)
            for t in self.tools:
                for config in t.configs:
                    if config.derived_from and config.derived_from.canvas_x != 0 and config.canvas_x != 0:
                        parent = config.derived_from
                        if parent.tool == t:
                            if t.display_horizontal:
                                self.draw_line(parent.canvas_x + parent.width/2, parent.canvas_y, 
                                                        config.canvas_x - config.width/2, config.canvas_y, 
                                                        fill="#9e9e9e", width=2, dash=(2, 4), arrow=tk.LAST, smooth=True)
                            else:
                                edge_offset = parent.width/2
                                self.draw_line(parent.canvas_x + edge_offset, parent.canvas_y, 
                                                        config.canvas_x + edge_offset, config.canvas_y, 
                                                        fill="#9e9e9e", width=2, dash=(2, 4), arrow=tk.LAST, smooth=True)
                        else:
                            self.draw_line(parent.canvas_x, parent.canvas_y + 20, config.canvas_x, config.canvas_y - 20, 
                                                    fill="#9e9e9e", width=2, dash=(2, 4), arrow=tk.LAST, smooth=True)

        # --- 3. Draw The Digital Thread (Context Links - Red dashed) ---
        if self.active_gc and self.visibility["Context Resolution"]:
            for config in self.active_gc.linked_configs.values():
                if config.canvas_x != 0: 
                    if config.id in self.active_gc_link_coords:
                        start_x, start_y = self.active_gc_link_coords[config.id]
                    else:
                        start_x, start_y = self.active_gc.canvas_x, self.active_gc.canvas_y + 25
                        
                    end_x, end_y = config.canvas_x, config.canvas_y - config.height/2
                    mid_y = (start_y + end_y) / 2
                    self.draw_line(start_x, start_y, start_x, mid_y, end_x, mid_y, end_x, end_y, 
                                            smooth=True, fill="#d32f2f", width=2, dash=(6, 4), arrow=tk.LAST)

        # --- 3.5 Draw Artifact Links (Blue solid) ---
        if self.visibility["Artifact Link"]:
            for tool in self.tools:
                for c in tool.configs:
                    for art in c.artifacts:
                        start_coords = self.render_coords.get((c.id, art.id))
                        if not start_coords: continue
                        
                        for target_art in art.links:
                            # 1. Try resolving link entirely within the SAME configuration
                            target_coords = self.render_coords.get((c.id, target_art.id))
                            
                            # 2. Try resolving cross-config (find any rendered instance)
                            if not target_coords:
                                for (cid, aid), coords in self.render_coords.items():
                                    if aid == target_art.id:
                                        target_coords = coords
                                        break
                                        
                            if target_coords:
                                self.draw_line(start_coords[0] + 50, start_coords[1], target_coords[0] + 50, target_coords[1], 
                                                        fill="#1976d2", width=1.5, arrow=tk.LAST, smooth=True)

        self._draw_legend(width, height)
        self.update_minimap()

    def _draw_legend(self, width: int, height: int):
        leg_x, leg_y = 20, height - 100
        self.canvas.create_rectangle(leg_x, leg_y, leg_x + 550, leg_y + 80, fill="white", outline="#cfd8dc")
        self.canvas.create_text(leg_x + 40, leg_y + 20, text="LEGEND & VISIBILITY TOGGLES:", font=("Segoe UI", 9, "bold"))
        
        def draw_cb(x, y, label, key, icon_func):
            is_on = self.visibility.get(key, False)
            cb_tag = (f"LEGEND_CB::{key}",)
            
            self.canvas.create_rectangle(x-2, y-6, x+150, y+18, fill="white", outline="", tags=cb_tag)
            self.canvas.create_rectangle(x, y, x+12, y+12, fill="white", outline="#90a4ae", tags=cb_tag)
            if is_on:
                self.canvas.create_line(x+2, y+2, x+10, y+10, fill="#1565c0", width=2, tags=cb_tag)
                self.canvas.create_line(x+10, y+2, x+2, y+10, fill="#1565c0", width=2, tags=cb_tag)
            
            icon_func(x+25, y+6, cb_tag)
            self.canvas.create_text(x+60 if "Artifact" not in label else x+75, y+6, text=label, font=("Segoe UI", 9), anchor=tk.W, tags=cb_tag)

        draw_cb(leg_x + 20, leg_y + 40, "Stream", "Stream", 
                  lambda cx, cy, tag: self.canvas.create_rectangle(cx, cy-6, cx+20, cy+6, fill="#fff3e0", outline="#ff9800", tags=tag))
        
        draw_cb(leg_x + 130, leg_y + 40, "Baseline", "Baseline", 
                  lambda cx, cy, tag: self.canvas.create_rectangle(cx, cy-6, cx+20, cy+6, fill="#e8f5e9", outline="#4caf50", tags=tag))
        
        draw_cb(leg_x + 240, leg_y + 40, "Branch", "Branch", 
                  lambda cx, cy, tag: self.canvas.create_line(cx, cy, cx+30, cy, fill="#9e9e9e", dash=(2,4), width=2, arrow=tk.LAST, tags=tag))
                  
        draw_cb(leg_x + 350, leg_y + 40, "Context Resolution", "Context Resolution", 
                  lambda cx, cy, tag: self.canvas.create_line(cx, cy, cx+30, cy, fill="#d32f2f", dash=(4,2), width=2, tags=tag))
        
        draw_cb(leg_x + 20, leg_y + 60, "Artifact Link", "Artifact Link", 
                  lambda cx, cy, tag: self.canvas.create_line(cx, cy, cx+30, cy, fill="#1976d2", width=1.5, arrow=tk.LAST, tags=tag))

    # ==========================================
    # MODAL DIALOGS & HISTORY 
    # ==========================================

    def _show_version_history(self, art: ArtifactVersion):
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Artifact Lineage: {art.name}")
        dialog.geometry("380x450")
        dialog.transient(self.root)
        dialog.grab_set()

        root_x, root_y = self.root.winfo_rootx(), self.root.winfo_rooty()
        dialog.geometry(f"+{root_x + 100}+{root_y + 100}")
        
        ttk.Label(dialog, text=f"Version Lineage for {art.name}", font=("Segoe UI", 11, "bold")).pack(pady=10)
        
        history = []
        curr = art
        while curr:
            history.append(curr)
            curr = curr.predecessor
            
        history.reverse()
        
        frame = ttk.Frame(dialog)
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        
        v_canvas = tk.Canvas(frame, bg="#eceff1", highlightthickness=0)
        v_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=v_canvas.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        v_canvas.configure(yscrollcommand=scrollbar.set)
        
        inner_frame = ttk.Frame(v_canvas, style="TFrame")
        v_canvas.create_window((0, 0), window=inner_frame, anchor="nw")
        
        y_offset = 20
        for i, item in enumerate(history):
            is_target = (item == art)
            box_bg = "#bbdefb" if is_target else "#ffffff"
            box_out = "#1565c0" if is_target else "#90caf9"
            
            v_canvas.create_rectangle(30, y_offset, 310, y_offset+35, fill=box_bg, outline=box_out, width=2)
            v_canvas.create_text(170, y_offset+17, text=f"{item.name} [{item.concept.tool.name}]", font=("Segoe UI", 9, "bold" if is_target else "normal"))
            
            if i < len(history) - 1:
                v_canvas.create_line(170, y_offset+35, 170, y_offset+65, fill="#ab47bc", arrow=tk.LAST, width=2)
            
            y_offset += 65
            
        inner_frame.update_idletasks()
        v_canvas.config(scrollregion=v_canvas.bbox("all"))

        ttk.Button(dialog, text="Close", command=dialog.destroy).pack(pady=10)

    def _start_link_pull(self, target_conf: LocalConfig):
        self.link_pull_target_conf = target_conf
        self.log_sys(f"Link Transfer Mode:\nTarget is '{target_conf.name}'.\nLeft-click the SOURCE config box to pull links from, or click background to cancel.")
        self.redraw_canvas()

    def _execute_link_pull(self, target_conf: LocalConfig, source_conf: LocalConfig):
        dialog = tk.Toplevel(self.root)
        dialog.title("Transfer Links & Artifacts")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        root_x, root_y = self.root.winfo_rootx(), self.root.winfo_rooty()
        root_width, root_height = self.root.winfo_width(), self.root.winfo_height()
        dialog.geometry(f"480x280+{root_x + root_width//2 - 240}+{root_y + root_height//2 - 140}")

        result = {}

        context_text = (f"Pulling links FROM:\t{source_conf.name} ({source_conf.config_type})\n"
                        f"Targeting TO:\t\t{target_conf.name} ({target_conf.config_type})\n\n"
                        "The system matches artifacts by their concept name. By default, only links for "
                        "artifacts that already exist in the target will be transferred.")
        ttk.Label(dialog, text=context_text, wraplength=450, font=("Segoe UI", 9)).pack(pady=10, padx=15, anchor=tk.W)

        action_var = tk.StringVar(value="copy")
        
        rb_frame = ttk.Frame(dialog)
        rb_frame.pack(fill=tk.X, padx=15)
        
        ttk.Radiobutton(rb_frame, text="Copy Links (Preserve in source)", variable=action_var, value="copy").pack(anchor=tk.W, pady=2)
        rb_move = ttk.Radiobutton(rb_frame, text="Move Links (Remove from source)", variable=action_var, value="move")
        rb_move.pack(anchor=tk.W, pady=2)
        
        if source_conf.config_type == 'Baseline':
            rb_move.config(state=tk.DISABLED)
            
        copy_missing_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(dialog, text="Also copy artifacts from Source that do NOT exist in Target", 
                        variable=copy_missing_var).pack(anchor=tk.W, padx=15, pady=15)

        def on_ok():
            result['action'] = action_var.get()
            result['copy_missing'] = copy_missing_var.get()
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Execute Transfer", command=on_ok).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=10)

        self.root.wait_window(dialog)
        
        if not result:
            self.log_sys("Link transfer cancelled.")
            return

        action = result['action']
        copy_missing = result['copy_missing']

        links_copied = 0
        links_moved = 0
        arts_copied = 0
        
        # Pull links based on matching concepts
        for s_art in source_conf.artifacts:
            concept_id = s_art.concept.id
            t_art = target_conf.selections.get(concept_id)
            
            if t_art:
                for link in list(s_art.links):
                    if link not in t_art.links:
                        t_art.links.append(link)
                        if action == "copy": links_copied += 1
                        else: links_moved += 1
                            
                    if action == "move" and link in s_art.links:
                        s_art.links.remove(link)
            elif copy_missing:
                # Add existing concept version to target
                target_conf.selections[concept_id] = s_art
                arts_copied += 1
                        
        msg = f"Transfer Complete: '{source_conf.name}' ➔ '{target_conf.name}'\n"
        msg += f" • Links {'Copied' if action == 'copy' else 'Moved'}: {links_copied + links_moved}\n"
        if copy_missing:
            msg += f" • Concepts Added to Target: {arts_copied}"
            
        self.log_sys(msg)
        self.redraw_canvas()

    def _set_link_source(self, art: ArtifactVersion):
        self.link_source_artifact = art
        self.log_sys(f"Linking Mode Active:\nSource is '{art.name}'.\nLeft-click another artifact version (⚙️ menu) to bind.")
        self.redraw_canvas()

    def _bind_link(self, target: ArtifactVersion):
        if self.link_source_artifact:
            if target not in self.link_source_artifact.links:
                self.link_source_artifact.links.append(target)
                self.log_sys(f"Link bound: '{self.link_source_artifact.name}' -> '{target.name}'.")
            self.link_source_artifact = None
            self.redraw_canvas()

    def _cancel_link(self):
        self.link_source_artifact = None
        self.log_sys("Linking mode cancelled.")
        self.redraw_canvas()

    def _remove_link(self, source: ArtifactVersion, target: ArtifactVersion):
        if target in source.links:
            source.links.remove(target)
            self.log_sys(f"Link severed: '{source.name}' -X-> '{target.name}'.")
            self.redraw_canvas()

if __name__ == "__main__":
    root = tk.Tk()
    app = OSLCPlaygroundApp(root)
    root.mainloop()
