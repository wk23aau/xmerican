
import React, { useState, useRef, useEffect, useCallback } from 'react';
import { createRoot } from 'react-dom/client';
import { 
  Upload, 
  Scan, 
  Ruler, 
  Crosshair, 
  Layers, 
  Info, 
  ChevronRight, 
  MousePointer2, 
  Loader2,
  Trash2,
  Maximize2,
  Download,
  FileUp,
  Globe,
  Send,
  CheckCircle2,
  AlertCircle,
  Cloud,
  Target,
  Zap,
  Copy,
  Hash,
  ShieldAlert,
  ZoomIn,
  Move,
  Axis3d
} from 'lucide-react';
import { GoogleGenAI, Type } from "@google/genai";

// --- Types & Interfaces ---

interface UIElement {
  id: string;
  label: string;
  type: string;
  box_2d: [number, number, number, number]; // [ymin, xmin, ymax, xmax] normalized 0-1000
}

interface ExportData {
  version: string;
  timestamp: string;
  imageDimensions: { width: number; height: number } | null;
  elements: UIElement[];
}

// --- Utils ---

const boxToPx = (box: [number, number, number, number], imgWidth: number, imgHeight: number) => {
  const [ymin, xmin, ymax, xmax] = box;
  return {
    top: (ymin / 1000) * imgHeight,
    left: (xmin / 1000) * imgWidth,
    width: ((xmax - xmin) / 1000) * imgWidth,
    height: ((ymax - ymin) / 1000) * imgHeight,
  };
};

// --- Components ---

const App: React.FC = () => {
  const [image, setImage] = useState<string | null>(null);
  const [elements, setElements] = useState<UIElement[]>([]);
  const [isScanning, setIsScanning] = useState(false);
  const [isProbing, setIsProbing] = useState(false);
  const [probeLocation, setProbeLocation] = useState<{ x: number, y: number } | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [imageDimensions, setImageDimensions] = useState<{ width: number; height: number } | null>(null);
  const [mousePos, setMousePos] = useState<{ x: number, y: number } | null>(null);
  const [copyFeedback, setCopyFeedback] = useState(false);
  
  // App Modes
  const [interactMode, setInteractMode] = useState<'inspect' | 'probe'>('inspect');
  const [measureMode, setMeasureMode] = useState<'standard' | 'center'>('standard');
  const [viewMode, setViewMode] = useState<'fit' | 'original'>('fit');
  const [coordSystem, setCoordSystem] = useState<'top-left' | 'center'>('top-left');
  
  // Remote Export States
  const [remoteUrl, setRemoteUrl] = useState('');
  const [isRemoteExporting, setIsRemoteExporting] = useState(false);
  const [remoteExportStatus, setRemoteExportStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [pushErrorMessage, setPushErrorMessage] = useState<string | null>(null);
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const importInputRef = useRef<HTMLInputElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Check for protocol mismatch (Mixed Content)
  const isProtocolMismatch = window.location.protocol === 'https:' && remoteUrl.startsWith('http:');

  // Monitor image resize to keep overlays in sync
  useEffect(() => {
    if (!imageRef.current) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        // Use contentRect for precise content box dimensions
        const { width, height } = entry.contentRect;
        // Avoid infinite loops by checking if values actually changed
        setImageDimensions((prev) => {
          if (prev?.width === width && prev?.height === height) return prev;
          return { width, height };
        });
      }
    });

    observer.observe(imageRef.current);
    return () => observer.disconnect();
  }, [image, viewMode]);

  const handleUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (event) => {
        setImage(event.target?.result as string);
        setElements([]);
        setSelectedId(null);
        setRemoteExportStatus('idle');
        setProbeLocation(null);
        // Reset view mode on new upload
        setViewMode('fit');
      };
      reader.readAsDataURL(file);
    }
  };

  const onImageLoad = (e: React.SyntheticEvent<HTMLImageElement>) => {
    const { width, height } = e.currentTarget;
    setImageDimensions({ width, height });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!imageRef.current || !imageDimensions) return;
    const rect = imageRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
    const y = Math.max(0, Math.min(e.clientY - rect.top, rect.height));
    setMousePos({ x, y });
  };

  const runAnalysis = async (point?: { x: number, y: number }) => {
    if (!image) return;
    
    const isTargeted = !!point;
    if (isTargeted) {
      setIsProbing(true);
      setProbeLocation(point);
    } else {
      setIsScanning(true);
    }
    
    setRemoteExportStatus('idle');
    setPushErrorMessage(null);
    
    try {
      const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });
      const base64Data = image.split(',')[1];
      
      const promptText = isTargeted 
        ? `Identify the UI element at (${point.x}, ${point.y}) normalized. Return JSON object with 'label', 'type', and 'box_2d'.`
        : "Identify all UI elements in this screenshot. Return JSON array with 'label', 'type', and 'box_2d'.";

      const response = await ai.models.generateContent({
        model: 'gemini-3-pro-preview',
        contents: {
          parts: [{ inlineData: { data: base64Data, mimeType: 'image/png' } }, { text: promptText }],
        },
        config: {
          responseMimeType: "application/json",
          responseSchema: isTargeted 
            ? {
                type: Type.OBJECT,
                properties: {
                  label: { type: Type.STRING },
                  type: { type: Type.STRING },
                  box_2d: { type: Type.ARRAY, items: { type: Type.NUMBER } },
                },
                required: ["label", "type", "box_2d"],
              }
            : {
                type: Type.ARRAY,
                items: {
                  type: Type.OBJECT,
                  properties: {
                    label: { type: Type.STRING },
                    type: { type: Type.STRING },
                    box_2d: { type: Type.ARRAY, items: { type: Type.NUMBER } },
                  },
                  required: ["label", "type", "box_2d"],
                },
              },
        },
      });

      const text = response.text;
      if (!text) throw new Error("No response text");
      
      const parsed = JSON.parse(text);
      const newElements = isTargeted ? [parsed] : parsed;
      
      const elementsWithIds = newElements.map((el: any, index: number) => ({
        ...el,
        id: `el-${Date.now()}-${index}`
      }));

      if (isTargeted) {
        setElements(prev => [...prev, ...elementsWithIds]);
        setSelectedId(elementsWithIds[0].id);
      } else {
        setElements(elementsWithIds);
      }
    } catch (error) {
      console.error("AI Analysis failed:", error);
    } finally {
      setIsScanning(false);
      setIsProbing(false);
    }
  };

  const handleCanvasClick = (e: React.MouseEvent) => {
    if (interactMode === 'probe' && imageRef.current && imageDimensions) {
      const rect = imageRef.current.getBoundingClientRect();
      const normX = Math.round(((e.clientX - rect.left) / rect.width) * 1000);
      const normY = Math.round(((e.clientY - rect.top) / rect.height) * 1000);
      runAnalysis({ x: normX, y: normY });
    }
  };

  const handleCopyCSS = (el: UIElement) => {
    if (!imageDimensions) return;
    const rect = boxToPx(el.box_2d, imageDimensions.width, imageDimensions.height);
    const css = `.element {\n  position: absolute;\n  top: ${Math.round(rect.top)}px;\n  left: ${Math.round(rect.left)}px;\n  width: ${Math.round(rect.width)}px;\n  height: ${Math.round(rect.height)}px;\n}`;
    navigator.clipboard.writeText(css);
    setCopyFeedback(true);
    setTimeout(() => setCopyFeedback(false), 2000);
  };

  const handleDownloadJson = () => {
    if (elements.length === 0) return;
    
    const payload: ExportData = {
      version: "1.0",
      timestamp: new Date().toISOString(),
      imageDimensions: imageDimensions,
      elements: elements
    };

    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "specmetric-export.json";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };
  
  const handleImportJson = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const content = e.target?.result as string;
        const data = JSON.parse(content) as ExportData;
        
        if (data.elements && Array.isArray(data.elements)) {
          setElements(data.elements);
          // If the imported data has image dimensions, we could warn if they don't match current image
          // but for simplicity we just load the data.
        } else {
            console.error("Invalid file format");
        }
      } catch (error) {
        console.error("Error parsing JSON", error);
      }
    };
    reader.readAsText(file);
    if (importInputRef.current) importInputRef.current.value = "";
  };

  const handleRemoteExport = async () => {
    if (elements.length === 0 || !remoteUrl) return;
    
    setIsRemoteExporting(true);
    setRemoteExportStatus('idle');
    setPushErrorMessage(null);

    const payload: ExportData = {
      version: "1.0",
      timestamp: new Date().toISOString(),
      imageDimensions: imageDimensions,
      elements: elements
    };

    console.info("%cSpecMetric AI: Dispatching remote push to:", "color: #3b82f6; font-weight: bold", remoteUrl);
    console.dir(payload);

    try {
      const response = await fetch(remoteUrl, {
        method: 'POST',
        mode: 'cors', // Explicitly request CORS
        headers: { 
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify(payload),
      });

      if (response.ok) {
        setRemoteExportStatus('success');
        console.log("%cSpecMetric AI: Push successful.", "color: #10b981; font-weight: bold");
      } else {
        console.error("%cSpecMetric AI: Push failed with status " + response.status, "color: #ef4444; font-weight: bold");
        setRemoteExportStatus('error');
        setPushErrorMessage(`Error: ${response.status}`);
      }
    } catch (err: any) {
      console.group("%cSpecMetric AI: Push Error Details", "color: #ef4444; font-weight: bold");
      console.error("The browser blocked the request. Possible reasons:");
      console.warn("1. CORS: The server at " + remoteUrl + " needs to allow origin " + window.location.origin);
      console.warn("2. Mixed Content: You are on HTTPS calling an HTTP endpoint. Use HTTPS for your API if possible.");
      console.warn("3. Network: The IP " + remoteUrl + " is not reachable from this environment.");
      console.error("Internal Error:", err.message);
      console.groupEnd();
      
      setRemoteExportStatus('error');
      setPushErrorMessage(isProtocolMismatch ? "Mixed Content Error" : "Network blocked");
    } finally {
      setIsRemoteExporting(false);
      // Auto reset status after 5 seconds if success, keep error visible longer
      if (remoteExportStatus === 'success') {
        setTimeout(() => setRemoteExportStatus('idle'), 3000);
      }
    }
  };

  const measurements = (() => {
    if (!imageDimensions) return null;
    const center = { x: imageDimensions.width / 2, y: imageDimensions.height / 2 };
    if (measureMode === 'center' && selectedId) {
      const sel = elements.find(e => e.id === selectedId);
      if (!sel) return null;
      const s = boxToPx(sel.box_2d, imageDimensions.width, imageDimensions.height);
      const sCenter = { x: s.left + s.width / 2, y: s.top + s.height / 2 };
      return { type: 'center', sCenter, imageCenter: center };
    }
    if (measureMode === 'standard' && selectedId && hoveredId && selectedId !== hoveredId) {
      const sel = elements.find(e => e.id === selectedId);
      const hov = elements.find(e => e.id === hoveredId);
      if (!sel || !hov) return null;
      const s = boxToPx(sel.box_2d, imageDimensions.width, imageDimensions.height);
      const h = boxToPx(hov.box_2d, imageDimensions.width, imageDimensions.height);
      return { type: 'standard', s, h };
    }
    return null;
  })();

  const getDisplayCoordinates = () => {
    if (!mousePos || !imageDimensions) return null;
    if (coordSystem === 'center') {
      const cx = Math.round(mousePos.x - imageDimensions.width / 2);
      const cy = Math.round(mousePos.y - imageDimensions.height / 2);
      return { x: cx, y: cy, label: 'CEN' };
    }
    return { x: Math.round(mousePos.x), y: Math.round(mousePos.y), label: 'PX' };
  };

  const displayCoords = getDisplayCoordinates();

  return (
    <div className="flex h-screen w-screen bg-zinc-950 text-zinc-100 overflow-hidden select-none font-sans">
      {/* Sidebar */}
      <div className="w-80 border-r border-zinc-800 flex flex-col bg-zinc-900/50 backdrop-blur-md z-20">
        <div className="p-6 border-b border-zinc-800 flex items-center gap-3">
          <div className="bg-blue-600 p-2 rounded-lg shadow-lg shadow-blue-900/20">
            <Ruler className="w-5 h-5 text-white" />
          </div>
          <h1 className="text-xl font-bold tracking-tight">SpecMetric <span className="text-blue-500">AI</span></h1>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          <div className="space-y-2">
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-[0.2em] px-2">Image Source</p>
            <button onClick={() => fileInputRef.current?.click()} className="w-full flex items-center gap-3 p-3 rounded-xl bg-zinc-800 hover:bg-zinc-700 transition-all border border-zinc-700 group">
              <Upload className="w-4 h-4 text-zinc-400 group-hover:text-blue-400" />
              <span className="text-sm font-medium">Upload Screenshot</span>
            </button>
            <input type="file" ref={fileInputRef} className="hidden" accept="image/*" onChange={handleUpload} />
            
            {image && (
              <button onClick={() => runAnalysis()} disabled={isScanning || isProbing} className={`w-full flex items-center justify-center gap-3 p-3 rounded-xl transition-all border ${isScanning ? 'bg-zinc-800 border-zinc-700 cursor-not-allowed text-zinc-500' : 'bg-blue-600 border-blue-500 hover:bg-blue-500 text-white shadow-lg'}`}>
                {isScanning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Scan className="w-4 h-4" />}
                <span className="text-sm font-medium">{isScanning ? 'Scanning...' : 'Full Layout Scan'}</span>
              </button>
            )}
          </div>
          
          <div className="space-y-2">
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-[0.2em] px-2">Data Management</p>
            <div className="flex gap-2">
                <button 
                    onClick={() => importInputRef.current?.click()} 
                    className="flex-1 flex items-center justify-center gap-2 p-2.5 rounded-xl bg-zinc-800 hover:bg-zinc-700 transition-all border border-zinc-700 text-xs font-medium text-zinc-300"
                >
                    <FileUp className="w-4 h-4" />
                    <span>Import JSON</span>
                </button>
                <input type="file" ref={importInputRef} className="hidden" accept=".json" onChange={handleImportJson} />
                
                <button 
                    onClick={handleDownloadJson} 
                    disabled={elements.length === 0}
                    className="flex-1 flex items-center justify-center gap-2 p-2.5 rounded-xl bg-zinc-800 hover:bg-zinc-700 transition-all border border-zinc-700 text-xs font-medium text-zinc-300 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    <Download className="w-4 h-4" />
                    <span>Export JSON</span>
                </button>
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-[0.2em] px-2">Web Integration</p>
            <div className="p-3 rounded-xl bg-zinc-900 border border-zinc-800 space-y-3">
              <div className="relative">
                <Globe className={`absolute left-2.5 top-2.5 w-3.5 h-3.5 ${isProtocolMismatch ? 'text-amber-500' : 'text-zinc-600'}`} />
                <input 
                  type="text" 
                  value={remoteUrl} 
                  onChange={(e) => { setRemoteUrl(e.target.value); setRemoteExportStatus('idle'); setPushErrorMessage(null); }} 
                  placeholder="API Webhook URL" 
                  className={`w-full bg-zinc-950 border rounded-lg py-2 pl-8 pr-3 text-xs focus:outline-none focus:ring-1 font-mono transition-colors ${
                    isProtocolMismatch ? 'border-amber-500/50 focus:ring-amber-500' : 'border-zinc-800 focus:ring-blue-500'
                  }`}
                />
                {isProtocolMismatch && (
                  <div className="mt-1.5 flex items-start gap-1.5 px-1">
                    <ShieldAlert className="w-3 h-3 text-amber-500 shrink-0 mt-0.5" />
                    <p className="text-[9px] text-amber-500/80 leading-tight">Secure apps (HTTPS) often block HTTP requests. Check your API protocol.</p>
                  </div>
                )}
              </div>
              
              <div className="space-y-2">
                <button 
                  onClick={handleRemoteExport} 
                  disabled={isRemoteExporting || !remoteUrl || elements.length === 0} 
                  className={`w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-xs font-bold transition-all border shadow-sm ${
                    remoteExportStatus === 'success' 
                      ? 'bg-emerald-600 border-emerald-500 text-white' 
                      : remoteExportStatus === 'error'
                        ? 'bg-red-600 border-red-500 text-white'
                        : 'bg-zinc-800 hover:bg-zinc-700 border-zinc-700 text-zinc-300 disabled:opacity-50'
                  }`}
                >
                  {isRemoteExporting ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : remoteExportStatus === 'success' ? (
                    <CheckCircle2 className="w-3.5 h-3.5" />
                  ) : remoteExportStatus === 'error' ? (
                    <AlertCircle className="w-3.5 h-3.5" />
                  ) : (
                    <Send className="w-3.5 h-3.5" />
                  )}
                  {isRemoteExporting ? 'Sending...' : remoteExportStatus === 'success' ? 'Data Sent' : remoteExportStatus === 'error' ? 'Push Failed' : 'Push Data'}
                </button>
                
                {pushErrorMessage && (
                  <div className="text-center animate-in fade-in slide-in-from-top-1 space-y-1">
                     <p className="text-[10px] text-red-400 font-medium">
                      {pushErrorMessage}
                    </p>
                    <p className="text-[9px] text-zinc-500">
                      (Export manually above)
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between px-2">
              <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-[0.2em]">Components ({elements.length})</p>
              {elements.length > 0 && <button onClick={() => setElements([])} className="text-zinc-500 hover:text-red-400 transition-colors"><Trash2 className="w-3.5 h-3.5" /></button>}
            </div>
            <div className="space-y-1">
              {elements.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-6 px-4 text-center space-y-3 opacity-30">
                  <Layers className="w-6 h-6" />
                  <p className="text-[10px] italic">Scan or use Probe to detect elements.</p>
                </div>
              ) : (
                elements.map((el) => (
                  <div key={el.id} onMouseEnter={() => setHoveredId(el.id)} onMouseLeave={() => setHoveredId(null)} onClick={() => setSelectedId(el.id === selectedId ? null : el.id)} className={`group flex items-center justify-between p-2.5 rounded-lg text-sm cursor-pointer transition-all border ${selectedId === el.id ? 'bg-blue-600/10 border-blue-500/50 text-blue-100' : 'bg-zinc-800/40 border-transparent hover:border-zinc-700 text-zinc-400 hover:text-zinc-200'}`}>
                    <div className="flex items-center gap-2.5 overflow-hidden">
                      <div className={`w-1 h-1 rounded-full shrink-0 ${selectedId === el.id ? 'bg-blue-400' : 'bg-zinc-600'}`} />
                      <div className="truncate">
                        <p className="font-medium truncate text-[11px] leading-tight">{el.label}</p>
                        <p className="text-[9px] uppercase tracking-tighter opacity-50 font-mono">{el.type}</p>
                      </div>
                    </div>
                    <ChevronRight className={`w-3.5 h-3.5 shrink-0 transition-transform ${selectedId === el.id ? 'rotate-90 text-blue-400' : 'opacity-0 group-hover:opacity-100'}`} />
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {selectedId && (
          <div className="p-4 border-t border-zinc-800 bg-zinc-950/80 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-blue-400">
                <Hash className="w-3.5 h-3.5" />
                <p className="text-[10px] font-bold uppercase tracking-wider">Selection Info</p>
              </div>
              <button 
                onClick={() => handleCopyCSS(elements.find(e => e.id === selectedId)!)}
                className={`flex items-center gap-1.5 px-2 py-1 rounded text-[10px] font-bold transition-all ${copyFeedback ? 'bg-emerald-600 text-white' : 'bg-zinc-800 hover:bg-zinc-700 text-zinc-300'}`}
              >
                {copyFeedback ? <CheckCircle2 className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                {copyFeedback ? 'Copied' : 'CSS'}
              </button>
            </div>
            {elements.filter(e => e.id === selectedId).map(el => {
              const rect = imageDimensions ? boxToPx(el.box_2d, imageDimensions.width, imageDimensions.height) : { top: 0, left: 0, width: 0, height: 0 };
              
              const displayProps = coordSystem === 'top-left' ? [
                { label: 'Top', val: Math.round(rect.top) },
                { label: 'Left', val: Math.round(rect.left) },
                { label: 'Width', val: Math.round(rect.width) },
                { label: 'Height', val: Math.round(rect.height) }
              ] : [
                { label: 'Cen X', val: Math.round((rect.left + rect.width/2) - (imageDimensions?.width || 0)/2) },
                { label: 'Cen Y', val: Math.round((rect.top + rect.height/2) - (imageDimensions?.height || 0)/2) },
                { label: 'Width', val: Math.round(rect.width) },
                { label: 'Height', val: Math.round(rect.height) }
              ];

              return (
                <div key={el.id} className="grid grid-cols-2 gap-2">
                  {displayProps.map(p => (
                    <div key={p.label} className="bg-zinc-900/80 border border-zinc-800/50 p-2 rounded-lg">
                      <p className="text-[8px] text-zinc-500 uppercase font-bold tracking-widest">{p.label}</p>
                      <p className="text-[11px] font-mono text-zinc-100">{p.val}px</p>
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Main Content */}
      <div className="flex-1 relative flex flex-col overflow-hidden bg-zinc-950 grid-bg">
        {/* Toolbar */}
        <div className="absolute top-6 left-1/2 -translate-x-1/2 flex items-center gap-2 p-1.5 rounded-2xl bg-zinc-900/90 backdrop-blur-2xl border border-zinc-800 shadow-2xl z-30 ring-1 ring-white/5">
          <div className="flex bg-zinc-950/50 p-1 rounded-xl border border-zinc-800/50">
            <button className={`p-2 rounded-lg transition-all flex items-center gap-2 ${interactMode === 'inspect' ? 'bg-zinc-100 text-zinc-950 shadow-sm' : 'text-zinc-500 hover:text-zinc-100'}`} onClick={() => setInteractMode('inspect')}>
              <MousePointer2 className="w-4 h-4" />
              <span className="text-[10px] font-bold uppercase tracking-wider hidden md:block">Inspect</span>
            </button>
            <button className={`p-2 rounded-lg transition-all flex items-center gap-2 ${interactMode === 'probe' ? 'bg-blue-600 text-white shadow-sm' : 'text-zinc-500 hover:text-zinc-100'}`} onClick={() => setInteractMode('probe')}>
              <Zap className={`w-4 h-4 ${isProbing ? 'animate-pulse' : ''}`} />
              <span className="text-[10px] font-bold uppercase tracking-wider hidden md:block">Probe</span>
            </button>
          </div>
          <div className="w-px h-6 bg-zinc-800 mx-1" />
          <button className={`p-2 rounded-xl transition-all ${measureMode === 'standard' ? 'bg-zinc-800 text-blue-400 border border-zinc-700' : 'text-zinc-500 hover:text-zinc-100'}`} onClick={() => setMeasureMode('standard')} title="Relative Distance"><Ruler className="w-4 h-4" /></button>
          <button className={`p-2 rounded-xl transition-all ${measureMode === 'center' ? 'bg-zinc-800 text-purple-400 border border-zinc-700' : 'text-zinc-500 hover:text-zinc-100'}`} onClick={() => setMeasureMode('center')} title="Center Point Anchor"><Target className="w-4 h-4" /></button>
          <div className="w-px h-6 bg-zinc-800 mx-1" />
          <button 
            className={`p-2 rounded-xl transition-all ${viewMode === 'original' ? 'bg-zinc-800 text-emerald-400 border border-zinc-700' : 'text-zinc-500 hover:text-zinc-100'}`} 
            onClick={() => setViewMode(viewMode === 'fit' ? 'original' : 'fit')} 
            title={viewMode === 'fit' ? "Switch to Actual Size" : "Fit to Screen"}
          >
            {viewMode === 'fit' ? <Maximize2 className="w-4 h-4" /> : <ZoomIn className="w-4 h-4" />}
          </button>
        </div>

        {/* Canvas Area */}
        <div className="flex-1 overflow-auto flex items-center justify-center p-20 custom-scrollbar scroll-smooth" ref={containerRef}>
          {image ? (
            <div 
              className="relative group shadow-[0_0_100px_rgba(0,0,0,0.8)]"
              onMouseMove={handleMouseMove}
              onMouseLeave={() => setMousePos(null)}
              onClick={handleCanvasClick}
            >
              <img 
                ref={imageRef} 
                src={image} 
                onLoad={onImageLoad} 
                className={`
                  ${viewMode === 'fit' ? 'max-w-[85vw] max-h-[85vh]' : 'max-w-none'} 
                  h-auto w-auto rounded-sm ring-1 ring-zinc-800 
                  ${interactMode === 'probe' ? 'cursor-crosshair' : 'cursor-default'}
                `} 
                draggable={false} 
              />
              
              {/* Mouse Tooltip & Guides */}
              {displayCoords && (
                <>
                  <div className="absolute top-0 bottom-0 w-px bg-white/10 pointer-events-none" style={{ left: mousePos!.x }} />
                  <div className="absolute left-0 right-0 h-px bg-white/10 pointer-events-none" style={{ top: mousePos!.y }} />
                  <div className="absolute bg-zinc-900/90 text-white text-[9px] px-1.5 py-0.5 rounded border border-white/20 pointer-events-none z-50 whitespace-nowrap font-mono shadow-xl" style={{ left: mousePos!.x + 12, top: mousePos!.y + 12 }}>
                    {displayCoords.label}: X:{displayCoords.x} Y:{displayCoords.y}
                  </div>
                </>
              )}

              {/* Probe Radar */}
              {probeLocation && imageDimensions && isProbing && (
                <div className="absolute pointer-events-none z-50 flex items-center justify-center" style={{ left: `${(probeLocation.x / 1000) * 100}%`, top: `${(probeLocation.y / 1000) * 100}%`, transform: 'translate(-50%, -50%)' }}>
                  <div className="w-16 h-16 border border-blue-500/50 rounded-full animate-ping" />
                  <div className="absolute w-2 h-2 bg-blue-500 rounded-full shadow-[0_0_15px_#3b82f6]" />
                </div>
              )}

              {/* Center Crosshair */}
              {imageDimensions && measureMode === 'center' && (
                <div className="absolute pointer-events-none z-40 flex items-center justify-center" style={{ left: '50%', top: '50%', transform: 'translate(-50%, -50%)' }}>
                  <div className="w-8 h-8 border border-purple-500/30 rounded-full animate-pulse" />
                  <div className="absolute w-6 h-[1px] bg-purple-500/50" />
                  <div className="absolute h-6 w-[1px] bg-purple-500/50" />
                </div>
              )}
              
              {/* Element Overlays */}
              {imageDimensions && elements.map((el) => {
                const rect = boxToPx(el.box_2d, imageDimensions.width, imageDimensions.height);
                const isSelected = selectedId === el.id;
                const isHovered = hoveredId === el.id;

                return (
                  <div 
                    key={el.id}
                    style={{ position: 'absolute', top: rect.top, left: rect.left, width: rect.width, height: rect.height, pointerEvents: isProbing ? 'none' : 'auto' }}
                    onMouseEnter={() => setHoveredId(el.id)}
                    onMouseLeave={() => setHoveredId(null)}
                    onClick={(e) => {
                      if (interactMode === 'inspect') {
                        e.stopPropagation();
                        setSelectedId(el.id === selectedId ? null : el.id);
                      }
                    }}
                    className={`transition-all duration-200 ${isSelected ? measureMode === 'center' ? 'ring-2 ring-purple-500 bg-purple-500/10 z-20 shadow-[0_0_15px_rgba(168,85,247,0.3)]' : 'ring-2 ring-blue-500 bg-blue-500/10 z-20 shadow-[0_0_15px_rgba(59,130,246,0.3)]' : isHovered ? 'ring-1 ring-white/50 bg-white/5 z-10 cursor-pointer' : 'ring-1 ring-blue-500/10 opacity-0 group-hover:opacity-100 hover:opacity-100'}`}
                  >
                    {(isSelected || isHovered) && (
                      <div className={`absolute -top-7 left-0 whitespace-nowrap px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-tighter shadow-md ${isSelected ? measureMode === 'center' ? 'bg-purple-600' : 'bg-blue-600' : 'bg-zinc-800 text-zinc-300'} text-white`}>
                        {el.label}
                      </div>
                    )}
                  </div>
                );
              })}

              {/* Measurement SVG Layer */}
              {measurements && !isProbing && (
                <svg className="absolute top-0 left-0 w-full h-full pointer-events-none z-30" style={{ overflow: 'visible' }}>
                  {measurements.type === 'center' && <CenterMeasurement x1={measurements.sCenter.x} y1={measurements.sCenter.y} x2={measurements.imageCenter.x} y2={measurements.imageCenter.y} />}
                  {measurements.type === 'standard' && (() => {
                    const { s, h } = measurements;
                    const lines: React.ReactNode[] = [];
                    if (h.top > s.top + s.height) lines.push(<DistanceLine key="v-gap-1" x1={s.left + s.width/2} y1={s.top + s.height} x2={s.left + s.width/2} y2={h.top} vertical />);
                    else if (s.top > h.top + h.height) lines.push(<DistanceLine key="v-gap-2" x1={s.left + s.width/2} y1={s.top} x2={s.left + s.width/2} y2={h.top + h.height} vertical />);
                    if (h.left > s.left + s.width) lines.push(<DistanceLine key="h-gap-1" x1={s.left + s.width} y1={s.top + s.height/2} x2={h.left} y2={s.top + s.height/2} />);
                    else if (s.left > h.left + h.width) lines.push(<DistanceLine key="h-gap-2" x1={s.left} y1={s.top + s.height/2} x2={h.left + h.width} y2={s.top + s.height/2} />);
                    return lines;
                  })()}
                </svg>
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center p-20 border-2 border-dashed border-zinc-800 rounded-3xl space-y-6 hover:border-zinc-700 transition-all cursor-pointer group" onClick={() => fileInputRef.current?.click()}>
              <div className="p-6 rounded-full bg-zinc-900 border border-zinc-800 group-hover:scale-110 transition-transform"><Upload className="w-12 h-12 text-zinc-600 group-hover:text-blue-500" /></div>
              <div className="text-center space-y-2">
                <p className="text-xl font-medium text-zinc-300">Start Project</p>
                <p className="text-[10px] text-zinc-500 font-mono uppercase tracking-widest">Upload UI Screenshot to begin</p>
              </div>
            </div>
          )}
        </div>

        {/* Status Bar */}
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 flex items-center gap-6 px-6 py-2.5 rounded-full bg-zinc-950/80 backdrop-blur-xl border border-white/5 text-[10px] text-zinc-400 uppercase tracking-widest font-bold shadow-2xl ring-1 ring-white/5">
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${isScanning || isProbing ? 'animate-ping bg-blue-500' : interactMode === 'probe' ? 'bg-blue-500' : 'bg-zinc-700'}`} /> 
            {isScanning || isProbing ? 'AI Processing' : interactMode === 'probe' ? 'Target Mode' : 'Standard'}
          </div>
          <div className="w-px h-3 bg-zinc-800" />
          <div className="hidden sm:block opacity-60">
            {measureMode === 'center' ? 'Measuring from Anchor' : 'Distance Inspector Active'}
          </div>
          <div className="w-px h-3 bg-zinc-800" />
          <div className="hidden sm:block opacity-60 font-mono text-emerald-400">
            {viewMode === 'fit' ? 'FIT' : '1:1'}
          </div>
          <div className="w-px h-3 bg-zinc-800" />
          <button 
            onClick={() => setCoordSystem(prev => prev === 'top-left' ? 'center' : 'top-left')}
            className="flex items-center gap-1.5 hover:text-white text-zinc-400 transition-colors"
            title="Toggle Coordinate Origin"
          >
            <Axis3d className="w-3 h-3" />
            <span>{coordSystem === 'top-left' ? 'TL Origin' : 'CTR Origin'}</span>
          </button>
        </div>
      </div>
    </div>
  );
};

// --- Sub-Components for SVG ---

const CenterMeasurement: React.FC<{ x1: number, y1: number, x2: number, y2: number }> = ({ x1, y1, x2, y2 }) => {
  const dx = Math.round(x1 - x2);
  const dy = Math.round(y1 - y2);
  const dist = Math.round(Math.sqrt(dx * dx + dy * dy));
  return (
    <g>
      <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#a855f7" strokeWidth="1.5" strokeDasharray="5 5" />
      <rect x={(x1 + x2) / 2 - 20} y={(y1 + y2) / 2 - 10} width="40" height="20" rx="4" fill="#a855f7" />
      <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 + 5} textAnchor="middle" fill="white" fontSize="10" fontWeight="bold" className="font-mono">{dist}</text>
      <g transform={`translate(${x1 > x2 ? x2 + 10 : x2 - 50}, ${y1 > y2 ? y1 - 25 : y1 + 15})`}>
        <text fill="#a855f7" fontSize="9" fontWeight="bold" className="font-mono">X:{dx}px</text>
        <text y="10" fill="#a855f7" fontSize="9" fontWeight="bold" className="font-mono">Y:{dy}px</text>
      </g>
    </g>
  );
};

const DistanceLine: React.FC<{ x1: number, y1: number, x2: number, y2: number, vertical?: boolean }> = ({ x1, y1, x2, y2, vertical = false }) => {
  const dist = Math.round(Math.abs(vertical ? y2 - y1 : x2 - x1));
  if (dist < 1) return null;
  return (
    <g>
      <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#3b82f6" strokeWidth="1.5" strokeDasharray="4 4" />
      <rect x={vertical ? x1 - 18 : (x1 + x2) / 2 - 18} y={vertical ? (y1 + y2) / 2 - 9 : y1 - 9} width="36" height="18" rx="4" fill="#3b82f6" />
      <text x={vertical ? x1 : (x1 + x2) / 2} y={vertical ? (y1 + y2) / 2 + 4 : y1 + 4} textAnchor="middle" fill="white" fontSize="9" fontWeight="bold" className="font-mono">{dist}</text>
    </g>
  );
};

const rootElement = document.getElementById('root');
if (rootElement) createRoot(rootElement).render(<App />);
