import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ApiError } from '../api/client';
import { fetchDataQuality } from '../api/quality';
import type { DataQuality, DataQualityCollege } from '../api/types';
import { EmptyState, PageHeader, Panel, StatTile } from '../components/ui';

export default function QualityPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<DataQuality | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetchDataQuality()
      .then(setData)
      .catch((err: ApiError) => setError(err.message || '加载失败'))
      .finally(() => setLoading(false));
  }, []);

  const total = data?.total ?? 0;
  const completeRate = total ? Math.round(((data?.complete ?? 0) / total) * 100) : 0;

  const columns: ColumnsType<DataQualityCollege> = [
    { title: '学院', dataIndex: 'college_name', width: 180, render: (v: string) => v ?? '（未填写）' },
    {
      title: '操作',
      key: 'action',
      width: 96,
      fixed: 'right',
      render: (_: unknown, r: DataQualityCollege) => (
        <Button
          type="link"
          size="small"
          style={{ padding: 0 }}
          onClick={() => navigate(`/students?college=${encodeURIComponent(r.college_name ?? '')}`)}
        >
          查看名单
        </Button>
      ),
    },
    { title: '学生数', dataIndex: 'total', width: 100, align: 'right' },
    { title: '信息完整', dataIndex: 'complete', width: 100, align: 'right' },
    {
      title: '缺专业',
      dataIndex: 'missing_major',
      width: 96,
      align: 'right',
      render: (v: number) => <span style={{ color: v ? 'var(--warn)' : 'var(--ink)' }}>{v}</span>,
    },
    {
      title: '缺班级',
      dataIndex: 'missing_class',
      width: 96,
      align: 'right',
      render: (v: number) => <span style={{ color: v ? 'var(--warn)' : 'var(--ink)' }}>{v}</span>,
    },
    {
      title: '缺入学年',
      dataIndex: 'missing_year',
      width: 100,
      align: 'right',
      render: (v: number) => <span style={{ color: v ? 'var(--warn)' : 'var(--ink)' }}>{v}</span>,
    },
    {
      title: '完整率',
      key: 'rate',
      width: 140,
      render: (_: unknown, r: DataQualityCollege) => {
        const rate = r.total ? Math.round((r.complete / r.total) * 100) : 0;
        return (
          <span style={{ color: rate >= 80 ? 'var(--ok)' : 'var(--warn)' }}>
            {rate}%
            <span style={{ marginLeft: 8, color: 'var(--faint)', fontSize: 12 }}>{r.complete}/{r.total}</span>
          </span>
        );
      },
    },
  ];

  return (
    <>
      <PageHeader
        title="数据质量"
        description="按现有库表统计信息完整性，定位缺失字段的学院与学生，把人工核对变成系统红黄绿。"
      />

      <div className="stat-row">
        <StatTile label="在校学生" value={total} hint="有效档案总数" />
        <StatTile label="信息完整" value={data?.complete ?? '—'} hint={`整体完整率 ${completeRate}%`} />
        <StatTile label="缺专业" value={data?.missing_major ?? '—'} hint="专业字段为空" />
        <StatTile label="缺班级" value={data?.missing_class ?? '—'} hint="班级字段为空" />
        <StatTile label="缺入学年" value={data?.missing_year ?? '—'} hint="入学年份为空" />
        <StatTile label="重名学生" value={data?.duplicate_names ?? '—'} hint="同名大于 1 人" />
      </div>

      {error && (
        <Alert style={{ marginTop: 12 }} type="error" showIcon message="加载失败" description={error} />
      )}

      <Panel
        title="各学院数据完整性"
        sub={`${data?.by_college.length ?? 0} 个学院`}
        flush
        extra={
          <Button size="small" onClick={() => navigate('/students')}>
            查看全部学生
          </Button>
        }
      >
        <Table<DataQualityCollege>
          rowKey="college_name"
          columns={columns}
          dataSource={data?.by_college ?? []}
          loading={loading}
          pagination={false}
          scroll={{ x: 820 }}
          locale={{ emptyText: <EmptyState title="暂无数据" hint="导入学生后此处显示统计" /> }}
        />
      </Panel>
    </>
  );
}
