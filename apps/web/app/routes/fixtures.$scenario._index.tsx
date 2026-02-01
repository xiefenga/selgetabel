import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { Loader2, ChevronLeft, Play, Tag, Database, FileText } from "lucide-react";

import { getFixtureScenario } from "~/lib/api";
import type { FixtureScenarioDetail } from "~/lib/api";

const FixtureScenarioPage = () => {
  const { scenario: scenarioId } = useParams();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scenario, setScenario] = useState<FixtureScenarioDetail | null>(null);

  useEffect(() => {
    if (!scenarioId) return;

    const fetchData = async () => {
      try {
        setLoading(true);
        const result = await getFixtureScenario(scenarioId);
        setScenario(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载失败");
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [scenarioId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-8 h-8 animate-spin text-emerald-600" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-red-500 text-center">
          <p className="font-medium">加载失败</p>
          <p className="text-sm text-gray-500">{error}</p>
        </div>
      </div>
    );
  }

  if (!scenario) {
    return null;
  }

  return (
    <div className="h-screen overflow-auto bg-linear-to-br from-gray-50 via-white to-emerald-50/30">
      <div className="max-w-4xl mx-auto px-6 py-8">

        {/* Header */}
        <div className="mb-8">
          <div className="flex items-start gap-2 -ml-10">
            <Link to="/fixtures" className="p-1 hover:bg-gray-100 rounded-full cursor-pointer" >
              <ChevronLeft className="w-6 h-6" />
            </Link>
            <div>
              <h1 className="text-2xl font-bold text-gray-900 mb-2">{scenario.name}</h1>
              <p className="text-gray-600 mb-4">{scenario.description}</p>
            </div>
          </div>

          {/* Tags */}
          {scenario.tags.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap mb-4">
              <Tag className="w-4 h-4 text-gray-400" />
              {scenario.tags.map((tag) => (
                <span
                  key={tag}
                  className="inline-flex items-center px-2.5 py-1 text-xs font-medium bg-emerald-100 text-emerald-700 rounded-full"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Datasets */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm mb-6 overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-100 bg-gray-50">
            <div className="flex items-center gap-2">
              <Database className="w-4 h-4 text-emerald-600" />
              <h2 className="font-semibold text-gray-900">数据集</h2>
            </div>
          </div>
          <div className="divide-y divide-gray-100">
            {scenario.datasets.map((dataset) => (
              <div key={dataset.file} className="px-5 py-3 flex items-center gap-3">
                <FileText className="w-4 h-4 text-gray-400" />
                <span className="font-mono text-sm text-gray-700">{dataset.file}</span>
                <span className="text-sm text-gray-500">- {dataset.description}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Test Cases */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-100 bg-gray-50">
            <div className="flex items-center gap-2">
              <Play className="w-4 h-4 text-emerald-600" />
              <h2 className="font-semibold text-gray-900">测试用例</h2>
              <span className="ml-2 text-sm text-gray-400">
                共 {scenario.cases.length} 个
              </span>
            </div>
          </div>
          <div className="divide-y divide-gray-100">
            {scenario.cases.map((testCase) => (
              <Link
                key={testCase.id}
                to={`/fixtures/${scenarioId}/${testCase.id}`}
                className="block px-5 py-4 hover:bg-emerald-50/50 transition-colors group"
              >
                <div className="flex items-center justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="font-medium text-gray-900 group-hover:text-emerald-700 transition-colors">
                        {testCase.name}
                      </h3>
                      <h4 className="text-sm text-gray-500">
                        {`${scenarioId}/${testCase.id}`}
                      </h4></div>
                    {testCase.tags.length > 0 && (
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {testCase.tags.map((tag) => (
                          <span
                            key={tag}
                            className="inline-flex items-center px-2 py-0.5 text-xs bg-gray-100 text-gray-600 rounded"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-emerald-600 opacity-0 group-hover:opacity-100 transition-opacity">
                      运行测试
                    </span>
                    <Play className="w-4 h-4 text-emerald-600" />
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default FixtureScenarioPage;
