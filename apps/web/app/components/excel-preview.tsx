import { useEffect, useRef } from "react";
import "@js-preview/excel/lib/index.css";


interface Props {
  fileUrl: string;
  className?: string;
}

const ExcelPreview = ({ fileUrl, className }: Props) => {

  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let previewer: any | undefined;
    let cancelled = false;

    const run = async () => {
      if (!containerRef.current) return;

      // 仅在浏览器端加载，避免 SSR 阶段触发 window is not defined
      const { default: jsPreviewExcel } = await import("@js-preview/excel");

      if (cancelled || !containerRef.current) return;

      previewer = jsPreviewExcel.init(containerRef.current);
      await previewer.preview(fileUrl);
    };

    run();

    return () => {
      cancelled = true;
      previewer?.destroy?.();
    };
  }, [fileUrl]);

  return (
    <div ref={containerRef} className={className} />
  )
}

export default ExcelPreview