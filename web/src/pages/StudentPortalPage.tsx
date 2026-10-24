import { useMemo, useState } from 'react';
import {
  Button,
  Empty,
  Form,
  Input,
  Select,
  Spin,
  Table,
  Tag,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { CheckOutlined, CloseOutlined, IdcardOutlined, SendOutlined } from '@ant-design/icons';
import { PageHeader } from '../components/ui';
import { fmt } from '../demo/format';
import { useDemoData } from '../demo/useDemoData';

interface PortalForm {
  phone: string;
  parentName?: string;
  parentPhone?: string;
  address?: string;
}

type SubmissionStatus = '待审核' | '已通过' | '已退回';

interface Submission {
  id: string;
  uid: string;
  name: string;
  time: string;
  phone: string;
  parentName: string;
  parentPhone: string;
  address: string;
  status: SubmissionStatus;
}

function maskPhone(value: string): string {
  const digits = value.replace(/\D/g, '');
  if (digits.length === 11) return `${digits.slice(0, 3)}****${digits.slice(-4)}`;
  if (digits.length >= 4) return `****${digits.slice(-4)}`;
  return value || '—';
}

export default function StudentPortalPage() {
  const { data, error } = useDemoData();
  const [uid, setUid] = useState('');
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [overrides, setOverrides] = useState<Record<string, { phone: string; parentName: string; parentPhone: string; address: string }>>({});
  const [form] = Form.useForm<PortalForm>();

  const currentUid = uid || data?.students[0]?.uid || '';
  const student = useMemo(
    () => data?.students.find((item) => item.uid === currentUid) ?? null,
    [data, currentUid],
  );
  const override = student ? overrides[student.uid] : undefined;

  if (error) {
    return <div className="wb"><Tag color="red">演示数据加载失败：{error}</Tag></div>;
  }

  if (!data) {
    return (
      <div className="wb wb-loading">
        <Spin size="large" />
        <span>正在加载本地演示数据…</span>
      </div>
    );
  }

  const onSubmit = async (values: PortalForm) => {
    if (!student) return;
    const submission: Submission = {
      id: `${Date.now()}`,
      uid: student.uid,
      name: student.name,
      time: new Date().toLocaleString('zh-CN', { hour12: false }),
      phone: values.phone,
      parentName: values.parentName ?? '',
      parentPhone: values.parentPhone ?? '',
      address: values.address ?? '',
      status: '待审核',
    };
    setSubmissions((current) => [submission, ...current]);
    form.resetFields();
    void message.success('已提交给辅导员审核（本地演示，未写正式库）');
  };

  const review = (submission: Submission, approved: boolean) => {
    setSubmissions((current) =>
      current.map((item) => (item.id === submission.id ? { ...item, status: approved ? '已通过' : '已退回' } : item)),
    );
    if (approved) {
      setOverrides((current) => ({
        ...current,
        [submission.uid]: {
          phone: submission.phone,
          parentName: submission.parentName,
          parentPhone: submission.parentPhone,
          address: submission.address,
        },
      }));
    }
    void message.success(approved ? '已通过，字段进入本地演示档案' : '已退回，学生可修改后重提');
  };

  const columns: ColumnsType<Submission> = [
    { title: '学生', dataIndex: 'name', width: 150, render: (value: string, row) => <span className="wb-two-line"><b>{row.uid}</b><small>{value}</small></span> },
    { title: '提交时间', dataIndex: 'time', width: 160, render: (value: string) => <span className="wb-mono">{value}</span> },
    { title: '本人电话', dataIndex: 'phone', width: 120, render: (value: string) => <span className="wb-mono">{maskPhone(value)}</span> },
    { title: '家长 / 电话', dataIndex: 'parentName', render: (value: string, row) => <span className="wb-two-line"><b>{value || '—'}</b><small>{row.parentPhone ? maskPhone(row.parentPhone) : '—'}</small></span> },
    { title: '地址', dataIndex: 'address', render: (value: string) => <span className="wb-muted">{value || '—'}</span> },
    { title: '状态', dataIndex: 'status', width: 90, render: (value: SubmissionStatus) => <Tag color={value === '已通过' ? 'green' : value === '已退回' ? 'red' : 'orange'}>{value}</Tag> },
    {
      title: '审核',
      key: 'action',
      width: 150,
      render: (_, row) =>
        row.status === '待审核' ? (
          <span className="sp-actions">
            <Button size="small" type="link" icon={<CheckOutlined />} onClick={() => review(row, true)}>通过</Button>
            <Button size="small" type="link" danger icon={<CloseOutlined />} onClick={() => review(row, false)}>退回</Button>
          </span>
        ) : (
          <span className="wb-muted">—</span>
        ),
    },
  ];

  const pending = submissions.filter((item) => item.status === '待审核').length;
  const currentPhone = override?.phone ? maskPhone(override.phone) : student?.phone ?? '—';
  const completeness = [student?.phone !== '—', Boolean(override?.parentPhone), Boolean(override?.address)].filter(Boolean).length;

  return (
    <div className="wb">
      <PageHeader
        title="学生自助填报"
        description="学生用自己的 UID 登录，补充联系方式与家庭信息；辅导员审核后进入学生档案。演示版使用身份切换，不接真实学生账号。"
        extra={
          <div className="wb-badges">
            <span className="wb-badge is-local">LOCAL DEMO</span>
            <span className="wb-badge is-demo">演示数据 · 不写正式库</span>
          </div>
        }
      />

      <div className="co-identity">
        <span className="co-identity-label">演示学生身份</span>
        <Select
          showSearch
          value={currentUid}
          onChange={(value) => {
            setUid(value);
            form.resetFields();
          }}
          style={{ width: 300 }}
          optionFilterProp="label"
          options={data.students.map((item) => ({
            value: item.uid,
            label: `${item.uid} · ${item.name} · ${item.class_short || item.class_name}`,
          }))}
        />
        <span className="co-identity-note">正式版：学生账号登录，只能看到自己的 UID 与字段。</span>
      </div>

      {student ? (
        <div className="wb-grid sp-grid">
          <section className="wb-panel">
            <header className="wb-panel-head"><h2>我的信息</h2><span>UID {student.uid}</span></header>
            <div className="sp-profile">
              <div className="sp-avatar"><IdcardOutlined /></div>
              <div>
                <b>{student.name}</b>
                <p>{student.college} · {student.major}</p>
                <Tag color={student.status === '在籍' ? 'green' : 'orange'}>{student.status}</Tag>
              </div>
            </div>
            <div className="sp-fields">
              <div><span>班级</span><b>{student.class_short || student.class_name}</b></div>
              <div><span>辅导员</span><b>{student.counselor}</b></div>
              <div><span>本人电话</span><b>{currentPhone}</b></div>
              <div><span>身份证</span><b>{student.id_card}</b></div>
              <div><span>家长联系人</span><b>{override?.parentName || '待补充'}</b></div>
              <div><span>家长电话</span><b>{override?.parentPhone ? maskPhone(override.parentPhone) : '待补充'}</b></div>
              <div><span>常住地址</span><b>{override?.address || '待补充'}</b></div>
              <div><span>生源地</span><b>{student.source_region || '—'}</b></div>
            </div>
            <div className="sp-completeness">
              <div><span>信息完整度</span><b>{completeness}/3</b></div>
              <span className="sp-progress"><span style={{ width: `${(completeness / 3) * 100}%` }} /></span>
              <small>本人电话 / 家长联系方式 / 常住地址</small>
            </div>
            <p className="wb-note">页面只显示脱敏字段；原始值由本地数据管理员侧保存，不进入演示库。</p>
          </section>

          <section className="wb-panel">
            <header className="wb-panel-head"><h2>补充 / 更新信息</h2><span>提交后由辅导员审核</span></header>
            <Form<PortalForm> form={form} layout="vertical" onFinish={onSubmit}>
              <Form.Item name="phone" label="本人电话" rules={[{ required: true, message: '请输入本人电话' }, { pattern: /^1\d{10}$/, message: '请输入 11 位手机号' }]}>
                <Input placeholder="11 位手机号，提交后页面只显示掩码" maxLength={11} />
              </Form.Item>
              <Form.Item name="parentName" label="家长姓名">
                <Input placeholder="选填" />
              </Form.Item>
              <Form.Item name="parentPhone" label="家长电话" rules={[{ pattern: /^1\d{10}$/, message: '请输入 11 位手机号' }]}>
                <Input placeholder="选填，提交后只显示掩码" maxLength={11} />
              </Form.Item>
              <Form.Item name="address" label="常住地址">
                <Input placeholder="选填，只保留到市/区展示" />
              </Form.Item>
              <Button type="primary" htmlType="submit" icon={<SendOutlined />}>提交给辅导员审核</Button>
            </Form>
            <p className="wb-note">正式版会对字段变更留痕，敏感字段加密存储；演示版提交后仅在本页内存中保留。</p>
          </section>
        </div>
      ) : null}

      <section className="wb-panel wb-table-panel">
        <header className="wb-panel-head"><h2>辅导员审核队列</h2><span>{fmt(pending)} 条待审 · 演示版与学生在同一页面</span></header>
        {submissions.length ? (
          <Table<Submission>
            rowKey="id"
            size="middle"
            columns={columns}
            dataSource={submissions}
            pagination={false}
            scroll={{ x: 980 }}
          />
        ) : (
          <Empty description="还没有提交；在上方补一个电话试试" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </section>

      <p className="wb-footnote">{data.metrics.disclaimer} · 学生自助演示 · 审核通过后只更新本地演示档案</p>
    </div>
  );
}
