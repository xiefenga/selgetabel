import { Link } from "react-router";
import { useEffect, useState } from "react";
import { Loader2, FlaskConical, ChevronRight, Tag, Folder } from "lucide-react";

import { getFixtureList } from "~/lib/api";
import type { FixtureGroup, FixtureScenarioSummary, FixtureListResponse } from "~/lib/api";

const FixturesIndexPage = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<FixtureListResponse | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const result = await getFixtureList();
        setData(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载失败");
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

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

  if (!data) {
    return null;
  }

  // 按 group 分组 scenarios
  const groupedScenarios = data.groups.map((group) => ({
    ...group,
    scenarios: data.scenarios.filter((s) => s.group === group.id),
  }));

  return (
    <div className="h-screen overflow-auto bg-linear-to-br from-gray-50 via-white to-emerald-50/30">
      <div className="max-w-6xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-xl bg-linear-to-br from-emerald-500 to-teal-600 flex items-center justify-center">
              <FlaskConical className="w-5 h-5 text-white" />
            </div>
            <h1 className="text-2xl font-bold text-gray-900">Fixture 测试用例</h1>
          </div>
          <p className="text-gray-600 ml-13">
            选择一个场景和用例来运行测试，查看 SSE 流式数据输出
          </p>
        </div>

        {/* Groups */}
        <div className="space-y-8">
          {groupedScenarios.map((group) => (
            <div key={group.id} className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
              {/* Group Header */}
              <div className="px-6 py-4 bg-linear-to-r from-gray-50 to-white border-b border-gray-100">
                <div className="flex items-center gap-3">
                  <Folder className="w-5 h-5 text-emerald-600" />
                  <div>
                    <h2 className="font-semibold text-gray-900">{group.name}</h2>
                    <p className="text-sm text-gray-500">{group.description}</p>
                  </div>
                  <span className="ml-auto text-sm text-gray-400">
                    {group.scenario_count} 个场景
                  </span>
                </div>
              </div>

              {/* Scenarios */}
              <div className="divide-y divide-gray-100">
                {group.scenarios.map((scenario) => (
                  <ScenarioCard key={scenario.id} scenario={scenario} />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

interface ScenarioCardProps {
  scenario: FixtureScenarioSummary;
}

const ScenarioCard = ({ scenario }: ScenarioCardProps) => {
  return (
    <Link
      to={`/fixtures/${scenario.id}`}
      className="block px-6 py-4 hover:bg-emerald-50/50 transition-colors group"
    >
      <div className="flex items-center justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-1">
            <h3 className="font-medium text-gray-900 group-hover:text-emerald-700 transition-colors">
              {scenario.name}
            </h3>
            <span className="text-sm text-gray-400">
              {scenario.case_count} 个用例
            </span>
          </div>
          {scenario.tags.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <Tag className="w-3.5 h-3.5 text-gray-400" />
              {scenario.tags.map((tag) => (
                <span
                  key={tag}
                  className="inline-flex items-center px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-600 rounded"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
        <ChevronRight className="w-5 h-5 text-gray-400 group-hover:text-emerald-600 transition-colors" />
      </div>
    </Link>
  );
};

export default FixturesIndexPage;
