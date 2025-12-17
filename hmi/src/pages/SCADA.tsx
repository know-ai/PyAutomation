import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { Button } from "../components/Button";
import { useTranslation } from "../hooks/useTranslation";
import { useTheme } from "../hooks/useTheme";
import { ResponsiveGridLayout, Layout as GridLayoutType } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import clsx from "clsx";

// Tipos para objetos SCADA
export type ScadaObjectType = 
  | "tank"
  | "pump"
  | "valve"
  | "pipe"
  | "curve"
  | "gauge"
  | "flowmeter";

export interface ScadaObject {
  id: string;
  type: ScadaObjectType;
  x: number;
  y: number;
  w: number;
  h: number;
  properties: {
    [key: string]: any;
  };
}

const STORAGE_KEY = "scada_layout";
const PALETTE_STORAGE_KEY = "scada_palette_position";
const GRID_COLS = 24;
const GRID_ROW_HEIGHT = 10;
const MIN_OBJECT_SIZE = 2;

// Configuración de iconos disponibles
const PALETTE_ITEMS: Array<{
  type: ScadaObjectType;
  label: string;
  icon: string;
  defaultSize: { w: number; h: number };
}> = [
  { type: "tank", label: "Tank", icon: "Tank 16.svg", defaultSize: { w: 4, h: 8 } },
  { type: "pump", label: "Pump", icon: "Cool pump.svg", defaultSize: { w: 3, h: 3 } },
  { type: "valve", label: "Valve", icon: "Hand valve 4.svg", defaultSize: { w: 2, h: 2 } },
  { type: "pipe", label: "Pipe", icon: "Short horizontal pipe.svg", defaultSize: { w: 4, h: 1 } },
  { type: "curve", label: "90° Curve", icon: "90° curve 2.svg", defaultSize: { w: 2, h: 2 } },
  { type: "gauge", label: "Gauge", icon: "Analog gauge.svg", defaultSize: { w: 3, h: 3 } },
  { type: "flowmeter", label: "Flowmeter", icon: "Mass flowmeter.svg", defaultSize: { w: 3, h: 2 } },
];

// Función helper para obtener la URL del icono
function getIconUrl(iconName: string): string {
  const basePath = import.meta.env.VITE_BASE_PATH || "/hmi/";
  return `${basePath}industrial_pallete_icons/${iconName}`;
}

// Componente para renderizar objetos SCADA
function ScadaObjectRenderer({ obj, isEditMode, isDark }: { obj: ScadaObject; isEditMode: boolean; isDark: boolean }) {
  const paletteItem = PALETTE_ITEMS.find(item => item.type === obj.type);
  const iconUrl = paletteItem ? getIconUrl(paletteItem.icon) : "";

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        position: "relative",
        border: isEditMode ? `1px dashed ${isDark ? "#666" : "#ccc"}` : "none",
        borderRadius: "4px",
        overflow: "hidden",
        backgroundColor: isEditMode ? (isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.02)") : "transparent",
      }}
    >
      {iconUrl && (
        <img
          src={iconUrl}
          alt={paletteItem?.label}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "contain",
            pointerEvents: "none",
            filter: isDark ? "brightness(0.9)" : "none",
          }}
          onError={(e) => {
            console.error("Failed to load icon:", iconUrl);
            e.currentTarget.style.display = "none";
          }}
        />
      )}
      {isEditMode && (
        <div
          className="drag-handle"
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            cursor: "move",
            zIndex: 10,
          }}
        />
      )}
    </div>
  );
}

// Componente de paleta flotante arrastrable
function ScadaPalette({ 
  isVisible, 
  onDragStart,
  isDark 
}: { 
  isVisible: boolean; 
  onDragStart: (type: ScadaObjectType, defaultSize: { w: number; h: number }) => void;
  isDark: boolean;
}) {
  const { t } = useTranslation();
  const paletteRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState<{ x: number; y: number }>(() => {
    const saved = localStorage.getItem(PALETTE_STORAGE_KEY);
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch {
        return { x: window.innerWidth - 240, y: 80 };
      }
    }
    return { x: window.innerWidth - 240, y: 80 };
  });
  const [isDragging, setIsDragging] = useState(false);
  const dragStartPos = useRef<{ x: number; y: number }>({ x: 0, y: 0 });

  // Guardar posición de la paleta
  useEffect(() => {
    if (position) {
      localStorage.setItem(PALETTE_STORAGE_KEY, JSON.stringify(position));
    }
  }, [position]);

  // Manejar inicio del drag de la paleta
  const handlePaletteMouseDown = useCallback((e: React.MouseEvent) => {
    // Solo arrastrar si se hace clic en el header
    const target = e.target as HTMLElement;
    if (!target.closest('.palette-header')) return;
    
    setIsDragging(true);
    dragStartPos.current = {
      x: e.clientX - position.x,
      y: e.clientY - position.y,
    };
    e.preventDefault();
  }, [position]);

  // Manejar movimiento del mouse para arrastrar la paleta
  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      const newX = e.clientX - dragStartPos.current.x;
      const newY = e.clientY - dragStartPos.current.y;
      
      // Limitar dentro de la ventana
      const maxX = window.innerWidth - 200;
      const maxY = window.innerHeight - 100;
      
      setPosition({
        x: Math.max(0, Math.min(newX, maxX)),
        y: Math.max(0, Math.min(newY, maxY)),
      });
    };

    const handleMouseUp = () => {
      setIsDragging(false);
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isDragging]);

  if (!isVisible) return null;

  const bgColor = isDark ? "#252936" : "white";
  const borderColor = isDark ? "#3d4455" : "#ddd";
  const textColor = isDark ? "#e9ecef" : "#1f2937";
  const itemBgHover = isDark ? "rgba(255,255,255,0.1)" : "#f5f5f5";
  const itemBorder = isDark ? "#3d4455" : "#eee";

  return (
    <div
      ref={paletteRef}
      style={{
        position: "fixed",
        left: `${position.x}px`,
        top: `${position.y}px`,
        width: "200px",
        backgroundColor: bgColor,
        border: `1px solid ${borderColor}`,
        borderRadius: "8px",
        boxShadow: isDark 
          ? "0 4px 6px rgba(0,0,0,0.3)" 
          : "0 4px 6px rgba(0,0,0,0.1)",
        zIndex: 1000,
        maxHeight: "calc(100vh - 100px)",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        userSelect: "none",
      }}
    >
      <div
        className="palette-header"
        onMouseDown={handlePaletteMouseDown}
        style={{
          padding: "12px 15px",
          borderBottom: `1px solid ${borderColor}`,
          cursor: isDragging ? "grabbing" : "grab",
          backgroundColor: isDark ? "rgba(255,255,255,0.05)" : "#f8f9fa",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <h6 style={{ margin: 0, fontWeight: "bold", color: textColor, fontSize: "14px" }}>
          {t("scada.palette.title", "Industrial Objects")}
        </h6>
        <i 
          className="bi bi-arrows-move" 
          style={{ 
            color: isDark ? "#9ca3af" : "#6b7280",
            fontSize: "14px"
          }}
        />
      </div>
      <div 
        style={{ 
          display: "flex", 
          flexDirection: "column", 
          gap: "8px", 
          padding: "12px",
          overflowY: "auto",
          maxHeight: "calc(100vh - 200px)",
        }}
      >
        {PALETTE_ITEMS.map((item) => (
          <div
            key={item.type}
            draggable
            onDragStart={(e) => {
              e.dataTransfer.setData(
                "application/scada-object",
                JSON.stringify({ type: item.type, defaultSize: item.defaultSize })
              );
              e.dataTransfer.effectAllowed = "copy";
              onDragStart(item.type, item.defaultSize);
            }}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              padding: "10px",
              border: `1px solid ${itemBorder}`,
              borderRadius: "6px",
              cursor: "grab",
              transition: "all 0.2s ease",
              backgroundColor: "transparent",
              color: textColor,
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = itemBgHover;
              e.currentTarget.style.transform = "translateX(2px)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = "transparent";
              e.currentTarget.style.transform = "translateX(0)";
            }}
          >
            <img
              src={getIconUrl(item.icon)}
              alt={item.label}
              style={{
                width: "32px",
                height: "32px",
                objectFit: "contain",
                pointerEvents: "none",
                filter: isDark ? "brightness(0.9)" : "none",
              }}
              onError={(e) => {
                console.error("Failed to load palette icon:", item.icon);
                e.currentTarget.style.display = "none";
              }}
            />
            <span style={{ fontSize: "14px", fontWeight: 500 }}>{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function SCADA() {
  const { t } = useTranslation();
  const { isDark } = useTheme();
  const [isEditMode, setIsEditMode] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(1200);
  const [scadaObjects, setScadaObjects] = useState<ScadaObject[]>(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch {
        return [];
      }
    }
    return [];
  });

  // Persistir layout en localStorage
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(scadaObjects));
  }, [scadaObjects]);

  // Medir ancho del contenedor
  useEffect(() => {
    const updateWidth = () => {
      if (containerRef.current) {
        setContainerWidth(containerRef.current.offsetWidth);
      }
    };
    updateWidth();
    window.addEventListener("resize", updateWidth);
    return () => window.removeEventListener("resize", updateWidth);
  }, []);

  // Manejar drag desde la paleta
  const handlePaletteDragStart = useCallback((type: ScadaObjectType, defaultSize: { w: number; h: number }) => {
    // El drag se maneja en el evento onDrop del canvas
  }, []);

  // Manejar drop en el canvas
  const handleCanvasDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      console.log("🔵 handleCanvasDrop called", { isEditMode, hasCanvasRef: !!canvasRef.current });
      
      if (!isEditMode) {
        console.log("❌ Drop rejected: not in edit mode");
        return;
      }
      
      if (!canvasRef.current) {
        console.log("❌ Drop rejected: no canvas ref");
        return;
      }

      e.preventDefault();
      e.stopPropagation();

      const data = e.dataTransfer.getData("application/scada-object");
      console.log("📦 Drop data:", data);
      
      if (!data) {
        console.log("❌ Drop rejected: no data in dataTransfer");
        return;
      }

      try {
        const { type, defaultSize } = JSON.parse(data);
        console.log("✅ Parsed drop data:", { type, defaultSize });
        
        // Obtener el contenedor del grid layout para calcular coordenadas correctas
        const gridContainer = canvasRef.current.querySelector('.react-grid-layout') as HTMLElement;
        console.log("📐 Grid container found:", !!gridContainer);
        
        let rect: DOMRect;
        if (gridContainer) {
          rect = gridContainer.getBoundingClientRect();
        } else {
          // Fallback: usar el canvas directamente
          rect = canvasRef.current.getBoundingClientRect();
        }
        
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        console.log("📍 Drop coordinates:", { x, y, rect: { width: rect.width, height: rect.height } });
        
        // Convertir coordenadas de píxeles a grid
        const paddingX = 10;
        const paddingY = 10;
        const availableWidth = rect.width - (paddingX * 2);
        
        const gridX = Math.max(0, Math.min(
          Math.floor(((x - paddingX) / availableWidth) * GRID_COLS),
          GRID_COLS - defaultSize.w
        ));
        const gridY = Math.max(0, Math.floor((y - paddingY) / GRID_ROW_HEIGHT));

        console.log("🎯 Calculated grid position:", { gridX, gridY });

        const newObject: ScadaObject = {
          id: `scada-obj-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
          type,
          x: gridX,
          y: gridY,
          w: defaultSize.w,
          h: defaultSize.h,
          properties: {},
        };

        console.log("🆕 Creating new object:", newObject);
        setScadaObjects((prev) => {
          const updated = [...prev, newObject];
          console.log("💾 Updated objects array, new length:", updated.length);
          return updated;
        });
      } catch (error) {
        console.error("❌ Error processing drop:", error);
      }
    },
    [isEditMode]
  );

  // Referencia para evitar loops infinitos
  const isProcessingLayoutRef = useRef(false);
  const lastLayoutHashRef = useRef<string>("");
  
  // Manejar cambios en el layout (drag and drop, resize) SOLO en modo edición
  const handleLayoutChange = useCallback(
    (layout: GridLayoutType[]) => {
      if (!isEditMode || isProcessingLayoutRef.current) return;
      
      // Crear un hash del layout para comparar
      const layoutHash = JSON.stringify(
        layout
          .map(item => `${item.i}:${item.x},${item.y},${item.w},${item.h}`)
          .sort()
          .join('|')
      );
      
      // Si el layout no cambió, no hacer nada
      if (lastLayoutHashRef.current === layoutHash) {
        return;
      }
      
      // Marcar que estamos procesando
      isProcessingLayoutRef.current = true;
      lastLayoutHashRef.current = layoutHash;
      
      setScadaObjects((prev) => {
        const updated = prev.map((obj) => {
          const layoutItem = layout.find((item) => item.i === obj.id);
          if (layoutItem) {
            // Solo actualizar si realmente cambió
            if (
              layoutItem.x === obj.x &&
              layoutItem.y === obj.y &&
              layoutItem.w === obj.w &&
              layoutItem.h === obj.h
            ) {
              return obj;
            }
            return {
              ...obj,
              x: layoutItem.x,
              y: layoutItem.y,
              w: layoutItem.w,
              h: layoutItem.h,
            };
          }
          return obj;
        });
        
        // Actualizar el hash después de actualizar el estado
        const newHash = JSON.stringify(
          updated
            .map(obj => `${obj.id}:${obj.x},${obj.y},${obj.w},${obj.h}`)
            .sort()
            .join('|')
        );
        
        // Resetear el flag después de que React procese el update
        setTimeout(() => {
          isProcessingLayoutRef.current = false;
          lastLayoutHashRef.current = newHash;
        }, 50);
        
        return updated;
      });
    },
    [isEditMode]
  );
  
  // Sincronizar el hash cuando se agregan nuevos objetos
  useEffect(() => {
    if (!isProcessingLayoutRef.current) {
      const currentHash = JSON.stringify(
        scadaObjects
          .map(obj => `${obj.id}:${obj.x},${obj.y},${obj.w},${obj.h}`)
          .sort()
          .join('|')
      );
      lastLayoutHashRef.current = currentHash;
    }
  }, [scadaObjects.length]); // Solo cuando cambia el número de objetos

  // Eliminar objeto
  const handleDeleteObject = useCallback((id: string) => {
    if (!isEditMode) return;
    setScadaObjects((prev) => prev.filter((obj) => obj.id !== id));
  }, [isEditMode]);

  // Layout para react-grid-layout - mantener estable para evitar loops
  const gridLayout = useMemo<GridLayoutType[]>(() => {
    return scadaObjects.map((obj) => ({
      i: obj.id,
      x: obj.x,
      y: obj.y,
      w: Math.max(obj.w, MIN_OBJECT_SIZE),
      h: Math.max(obj.h, MIN_OBJECT_SIZE),
      minW: MIN_OBJECT_SIZE,
      minH: MIN_OBJECT_SIZE,
      static: !isEditMode,
      resizeHandles: isEditMode ? ["se", "sw", "ne", "nw", "e", "w", "s", "n"] : [],
    } as GridLayoutType & { resizeHandles?: string[] }));
  }, [scadaObjects, isEditMode]);

  const handleToggleEditMode = useCallback(() => {
    setIsEditMode((prev) => !prev);
  }, []);

  const canvasBg = isDark ? "#1a1d29" : "#f8f9fa";
  const canvasBorder = isDark ? "#3d4455" : "#ddd";
  const textColor = isDark ? "#e9ecef" : "#1f2937";
  const mutedText = isDark ? "#9ca3af" : "#6c757d";

  return (
    <div className="row" style={{ cursor: "default", position: "relative" }}>
      <div className="col-12">
        {isEditMode && (
          <div className="d-flex justify-content-between align-items-center mb-3">
            <h3 className="card-title m-0" style={{ color: textColor }}>
              {t("navigation.scada", "SCADA")}
            </h3>
            <div className="d-flex gap-2 align-items-center">
              <span className="badge bg-warning text-dark">
                {t("scada.editMode", "Edit Mode")}
              </span>
              <Button
                variant="danger"
                className="btn-sm"
                onClick={() => {
                  if (window.confirm(t("scada.confirmClear", "Clear all objects?"))) {
                    setScadaObjects([]);
                  }
                }}
              >
                <i className="bi bi-trash me-1"></i>
                {t("scada.clear", "Clear")}
              </Button>
            </div>
          </div>
        )}
        
        <div
          ref={containerRef}
          style={{ position: "relative", width: "100%", minHeight: "500px" }}
          onDoubleClick={handleToggleEditMode}
        >
          <div
            ref={canvasRef}
            onDragOver={(e) => {
              if (isEditMode) {
                e.preventDefault();
                e.stopPropagation();
                e.dataTransfer.dropEffect = "copy";
              }
            }}
            onDragEnter={(e) => {
              if (isEditMode) {
                e.preventDefault();
                e.stopPropagation();
              }
            }}
            onDrop={handleCanvasDrop}
            style={{
              width: "100%",
              height: "100%",
              position: "relative",
              backgroundColor: canvasBg,
              border: isEditMode ? `2px dashed ${canvasBorder}` : `1px solid ${canvasBorder}`,
              borderRadius: "8px",
              minHeight: "500px",
              transition: "all 0.3s ease",
            }}
          >
            {scadaObjects.length === 0 ? (
              <div
                className="text-center py-5"
                style={{
                  minHeight: "400px",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  pointerEvents: "none",
                }}
              >
                <i className="bi bi-diagram-3" style={{ fontSize: "4rem", color: mutedText }}></i>
                <h4 className="mt-3" style={{ color: textColor }}>{t("navigation.scada", "SCADA")}</h4>
                <p style={{ color: mutedText }}>
                  {isEditMode
                    ? t("scada.emptyEdit", "Double-click to exit edit mode. Drag objects from the palette to the canvas.")
                    : t("scada.emptyProduction", "Double-click to enter edit mode and start building your SCADA diagram.")}
                </p>
              </div>
            ) : (
              <div
                onDragOver={(e) => {
                  if (isEditMode) {
                    e.preventDefault();
                    e.stopPropagation();
                    e.dataTransfer.dropEffect = "copy";
                  }
                }}
                onDragEnter={(e) => {
                  if (isEditMode) {
                    e.preventDefault();
                    e.stopPropagation();
                  }
                }}
                onDrop={handleCanvasDrop}
                style={{ width: "100%", height: "100%", position: "relative" }}
              >
                <ResponsiveGridLayout
                  className="layout"
                  layouts={{ lg: gridLayout }}
                  cols={{ lg: GRID_COLS }}
                  rowHeight={GRID_ROW_HEIGHT}
                  width={containerWidth}
                  onLayoutChange={(layout, allLayouts) => {
                    if (isEditMode) {
                      const newLayout = (allLayouts.lg || layout) as GridLayoutType[];
                      handleLayoutChange(newLayout);
                    }
                  }}
                  isDraggable={isEditMode}
                  isResizable={isEditMode}
                  draggableHandle={isEditMode ? ".drag-handle" : undefined}
                  preventCollision={false}
                  compactType={null}
                  margin={[5, 5]}
                  containerPadding={[10, 10]}
                  breakpoints={{ lg: 0 }}
                  resizeHandles={isEditMode ? ["se", "sw", "ne", "nw", "e", "w", "s", "n"] : []}
                  onDragStop={() => {
                    // Asegurar que el flag se resetee después de drag
                    setTimeout(() => {
                      isProcessingLayoutRef.current = false;
                    }, 100);
                  }}
                  onResizeStop={() => {
                    // Asegurar que el flag se resetee después de resize
                    setTimeout(() => {
                      isProcessingLayoutRef.current = false;
                    }, 100);
                  }}
                >
                  {scadaObjects.map((obj) => (
                    <div
                      key={obj.id}
                      style={{
                        height: "100%",
                        width: "100%",
                        overflow: "visible",
                        position: "relative",
                      }}
                    >
                      <ScadaObjectRenderer obj={obj} isEditMode={isEditMode} isDark={isDark} />
                      {isEditMode && (
                        <button
                          onClick={() => handleDeleteObject(obj.id)}
                          style={{
                            position: "absolute",
                            top: "-8px",
                            right: "-8px",
                            width: "24px",
                            height: "24px",
                            borderRadius: "50%",
                            backgroundColor: "#dc3545",
                            color: "white",
                            border: "2px solid white",
                            cursor: "pointer",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            fontSize: "16px",
                            fontWeight: "bold",
                            zIndex: 1000,
                            padding: 0,
                            lineHeight: 1,
                            boxShadow: "0 2px 4px rgba(0,0,0,0.2)",
                            transition: "transform 0.2s ease",
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.transform = "scale(1.1)";
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.transform = "scale(1)";
                          }}
                          title={t("scada.delete", "Delete")}
                        >
                          ×
                        </button>
                      )}
                    </div>
                  ))}
                </ResponsiveGridLayout>
              </div>
            )}
          </div>
        </div>
        
        {/* Paleta flotante - solo visible en modo edición */}
        <ScadaPalette
          isVisible={isEditMode}
          onDragStart={handlePaletteDragStart}
          isDark={isDark}
        />
      </div>
    </div>
  );
}
