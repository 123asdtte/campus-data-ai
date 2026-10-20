import { useState } from 'react';
import { Alert, App, Button, InputNumber, Select, Table, Tag, Typography, Upload } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { UploadProps } from 'antd';
import { InboxOutlined, ReloadOutlined } from '@ant-design/icons';
import { ApiError } from '../api/client';
import { commitImport, fetchBatch, previewImport, validateImport } from '../api/imports';
import type {
  CommitResult,
  ImportIssue,
  PreviewResult,
  TargetType,
  ValidateResult,
} from '../api/types';
import { ISSUE_CODE_LABEL } from '../api/types';
import { EmptyState, PageHeader, Panel, StatusBadge } from '../components/ui';

const MAX_SIZE_MB = 10;

type BusyKind = 'preview' | 'validate' | 'commit' | null;

const STEPS = ['选择文件', '预览与映射', '校验结果', '导入完成'];

function issueColumns(): ColumnsType<ImportIssue> {
  return [
    {
      title: 'Excel 行号',
      dataIndex: 'row_number',
      width: 96,
      render: (value: number) => <span className="mono">{value}</span>,
    },
    { title: '字段', dataIndex: 'field_name', width: 130, render: (v) => v ?? '—' },
    {
      title: '异常类型',
      dataIndex: 'issue_code',
      width: 130,
      render: (value: string) => <Tag color="volcano">{ISSUE_CODE_LABEL[value] ?? value}</Tag>,
    },
    {
      title: '级别',
      dataIndex: 'severity',
      width: 86,
      render: (value: string) =>
        value === 'error' ? (
          <StatusBadge tone="danger" label="错误" />
        ) : (
          <StatusBadge tone="warning" label="警告" />
        ),
    },
    { title: '说明', dataIndex: 'issue_message' },
  ];
}

export default function ImportPage() {
  const { message, modal } = App.useApp();

  const [file, setFile] = useState<File | null>(null);
  const [target, setTarget] = useState<TargetType>('students');
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [validation, setValidation] = useState<ValidateResult | null>(null);
  const [commitResult, setCommitResult] = useState<CommitResult | null>(null);
  const [busy, setBusy] = useState<BusyKind>(null);
  const [restoreId, setRestoreId] = useState<number | null>(null);

  const stepIndex = commitResult ? 3 : validation ? 2 : preview ? 1 : 0;

  const beforeUpload: UploadProps['beforeUpload'] = (selected) => {
    if (!/\.(xlsx|xlsm|csv)$/i.test(selected.name)) {
      message.error('仅支持 .xlsx / .xlsm / .csv 文件');
      return Upload.LIST_IGNORE;
    }
    if (selected.size > MAX_SIZE_MB * 1024 * 1024) {
      message.error(`文件超过 ${MAX_SIZE_MB} MB 上限`);
      return Upload.LIST_IGNORE;
    }
    setFile(selected);
    setPreview(null);
    setValidation(null);
    setCommitResult(null);
    return false;
  };

  const handlePreview = async () => {
    if (!file) {
      message.warning('请先选择文件');
      return;
    }
    setBusy('preview');
    try {
      const result = await previewImport(file, target);
      setPreview(result);
      setValidation(null);
      setCommitResult(null);
      if (result.status === 'failed') {
        message.error('文件缺少必需列，无法继续校验');
      } else {
        message.success(`已解析 ${result.total_rows} 行`);
      }
    } catch (err) {
      message.error((err as ApiError).message);
    } finally {
      setBusy(null);
    }
  };

  const handleValidate = async () => {
    if (!preview) return;
    setBusy('validate');
    try {
      const result = await validateImport(preview.batch_id);
      setValidation(result);
      if (result.valid_rows === 0) {
        message.warning('没有可导入的有效记录');
      } else {
        message.success(`有效 ${result.valid_rows} 行，异常 ${result.invalid_rows} 行`);
      }
    } catch (err) {
      message.error((err as ApiError).message);
    } finally {
      setBusy(null);
    }
  };

  const doCommit = async (batchId: number) => {
    setBusy('commit');
    try {
      const result = await commitImport(batchId);
      setCommitResult(result);
      message.success(`导入完成，写入 ${result.inserted_rows} 条`);
    } catch (err) {
      const apiError = err as ApiError;
      if (apiError.status === 409) {
        message.warning(apiError.message);
      } else {
        message.error(apiError.message);
      }
    } finally {
      setBusy(null);
    }
  };

  const handleCommitClick = () => {
    if (!validation) return;
    modal.confirm({
      title: '确认导入',
      content: `将写入 ${validation.valid_rows} 条有效记录；${validation.invalid_rows} 条异常记录不会导入。提交后不可撤销。`,
      okText: '确认写入',
      cancelText: '再检查一下',
      onOk: () => doCommit(validation.batch_id),
    });
  };

  const handleRestore = async () => {
    if (!restoreId) {
      message.warning('请输入批次号');
      return;
    }
    setBusy('validate');
    try {
      const detail = await fetchBatch(restoreId);
      setPreview(null);
      if (detail.status === 'imported') {
        setValidation(null);
        setCommitResult({
          batch_id: detail.batch_id,
          batch_code: detail.batch_code,
          status: detail.status,
          inserted_rows: detail.valid_rows,
          skipped_rows: [],
          invalid_rows_excluded: detail.invalid_rows,
        });
        message.info('该批次已提交，仅展示结果');
      } else {
        setCommitResult(null);
        setValidation({
          batch_id: detail.batch_id,
          batch_code: detail.batch_code,
          status: detail.status,
          total_rows: detail.total_rows,
          valid_rows: detail.valid_rows,
          invalid_rows: detail.invalid_rows,
          error_count: detail.issues.filter((i) => i.severity === 'error').length,
          warning_count: detail.issues.filter((i) => i.severity === 'warning').length,
          column_mapping: {},
          issues: detail.issues,
        });
        message.info(`已恢复批次 ${detail.batch_code}`);
      }
    } catch (err) {
      message.error((err as ApiError).message);
    } finally {
      setBusy(null);
    }
  };

  const resetAll = () => {
    setFile(null);
    setPreview(null);
    setValidation(null);
    setCommitResult(null);
    setRestoreId(null);
  };

  const canCommit = Boolean(validation && validation.valid_rows > 0 && busy !== 'commit');

  const previewColumns: ColumnsType<Record<string, unknown>> =
    preview && preview.preview.length > 0
      ? Object.keys(preview.preview[0])
          .filter((key) => key !== '__row')
          .map((key) => ({
            title: preview.field_labels[key] ?? key,
            dataIndex: key,
            width: 150,
            render: (value: unknown) => (value === null || value === undefined ? '—' : String(value)),
          }))
      : [];

  return (
    <>
      <PageHeader
        title="数据导入"
        description="上传 Excel / CSV，先预览与校验，确认后才写入数据库。异常行不会入库。"
        extra={
          <Button onClick={resetAll} disabled={busy !== null}>
            新建导入
          </Button>
        }
      />

      <Panel flush>
        <div className="step-rail">
          {STEPS.map((label, index) => {
            const state = index < stepIndex ? 'is-done' : index === stepIndex ? 'is-active' : '';
            return (
              <div key={label} style={{ display: 'contents' }}>
                <div className={`step ${state}`}>
                  <span className="step-index">{index < stepIndex ? '✓' : index + 1}</span>
                  <span className="step-title">{label}</span>
                </div>
                {index < STEPS.length - 1 && <span className="step-line" />}
              </div>
            );
          })}
        </div>
      </Panel>

      <Panel
        title="01 选择文件"
        sub="支持 .xlsx / .csv，单文件 ≤ 10 MB、10,000 行"
        extra={
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Select
              size="small"
              value={target}
              style={{ width: 132 }}
              onChange={(value: TargetType) => {
                setTarget(value);
                setPreview(null);
                setValidation(null);
                setCommitResult(null);
              }}
              options={[
                { label: '学生信息', value: 'students' },
                { label: '学籍异动', value: 'student_changes' },
              ]}
            />
            <Button
              type="primary"
              onClick={() => void handlePreview()}
              loading={busy === 'preview'}
              disabled={!file || busy !== null}
            >
              上传并预览
            </Button>
          </div>
        }
      >
        <Upload.Dragger
          accept=".xlsx,.xlsm,.csv"
          maxCount={1}
          beforeUpload={beforeUpload}
          showUploadList={false}
          disabled={busy !== null}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">
            {file ? `已选择：${file.name}` : '点击或拖拽文件到此处'}
          </p>
          <p className="ant-upload-hint">
            {file
              ? `大小 ${(file.size / 1024).toFixed(0)} KB · 重新选择会覆盖当前文件`
              : '文件仅在服务端解析，不会上传到第三方'}
          </p>
        </Upload.Dragger>
      </Panel>

      {preview && (
        <Panel
          title="02 预览与列映射"
          sub={`批次 ${preview.batch_code}`}
          flush
          extra={
            <span style={{ fontSize: 12, color: 'var(--muted)' }}>
              共 {preview.total_rows} 行 · 目标：{preview.target_type === 'students' ? '学生信息' : '学籍异动'}
            </span>
          }
        >
          <div style={{ padding: '16px 16px 0' }}>
            {preview.missing_required.length > 0 && (
              <Alert
                type="error"
                showIcon
                style={{ marginBottom: 12 }}
                message="缺少必需列，无法继续"
                description={`缺少：${preview.missing_required.join('、')}。请按模板补齐表头后重新上传。`}
              />
            )}

            {preview.unmapped_columns.length > 0 && (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 12 }}
                message={`以下列未被识别，将被忽略：${preview.unmapped_columns.join('、')}`}
              />
            )}

            {Object.keys(preview.column_mapping).length > 0 && (
              <div className="map-list" style={{ marginBottom: 14 }}>
                {Object.entries(preview.column_mapping).map(([source, field]) => (
                  <span className="map-chip" key={source}>
                    {source}
                    <span className="arrow">→</span>
                    <span className="target">{preview.field_labels[field] ?? field}</span>
                  </span>
                ))}
              </div>
            )}
          </div>

          <Table<Record<string, unknown>>
            rowKey="__row"
            columns={previewColumns}
            dataSource={preview.preview}
            pagination={false}
            scroll={{ x: 'max-content' }}
            locale={{ emptyText: <EmptyState title="没有可预览的数据行" /> }}
          />

          <div className="action-bar">
            <span className="action-bar-note">预览与校验都不会写入数据库</span>
            <Button
              type="primary"
              onClick={() => void handleValidate()}
              loading={busy === 'validate'}
              disabled={preview.status === 'failed' || busy !== null}
            >
              开始校验
            </Button>
          </div>
        </Panel>
      )}

      {validation && (
        <Panel
          title="03 校验结果"
          sub={`批次 ${validation.batch_code}`}
          extra={<StatusBadge tone={validation.invalid_rows > 0 ? 'warning' : 'success'} label={validation.invalid_rows > 0 ? '存在异常行' : '全部通过'} />}
        >
          <div className="metric-row" style={{ marginBottom: 14 }}>
            <div className="metric is-success">
              <div className="metric-value">{validation.valid_rows}</div>
              <div className="metric-label">有效行</div>
            </div>
            <div className="metric is-danger">
              <div className="metric-value">{validation.invalid_rows}</div>
              <div className="metric-label">异常行</div>
            </div>
            <div className="metric">
              <div className="metric-value">{validation.total_rows}</div>
              <div className="metric-label">总行数</div>
            </div>
          </div>

          {validation.invalid_rows > 0 && (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 12 }}
              message={`${validation.invalid_rows} 行存在问题，这些行不会写入数据库`}
              description="可修正后重新上传，或在确认无误后仅导入有效行。"
            />
          )}

          <Table<ImportIssue>
            rowKey={(record) => `${record.row_number}-${record.issue_code}-${record.field_name ?? ''}`}
            columns={issueColumns()}
            dataSource={validation.issues}
            pagination={{ pageSize: 10, showSizeChanger: false }}
            scroll={{ x: 700 }}
            locale={{ emptyText: <EmptyState title="没有异常" hint="所有行都通过校验" /> }}
          />

          <div className="action-bar">
            <span className="action-bar-note">
              错误 {validation.error_count} · 警告 {validation.warning_count}
              {validation.valid_rows === 0 && ' · 没有有效记录，无法提交'}
            </span>
            <Button
              type="primary"
              danger
              onClick={handleCommitClick}
              loading={busy === 'commit'}
              disabled={!canCommit}
            >
              确认导入 {validation.valid_rows} 条
            </Button>
          </div>
        </Panel>
      )}

      {commitResult && (
        <Panel title="04 导入结果" sub={`批次 ${commitResult.batch_code}`}>
          <div className="metric-row">
            <div className="metric is-success">
              <div className="metric-value">{commitResult.inserted_rows}</div>
              <div className="metric-label">已写入</div>
            </div>
            <div className="metric is-warning">
              <div className="metric-value">{commitResult.skipped_rows.length}</div>
              <div className="metric-label">跳过</div>
            </div>
            <div className="metric">
              <div className="metric-value">{commitResult.invalid_rows_excluded}</div>
              <div className="metric-label">异常未导入</div>
            </div>
          </div>

          {commitResult.skipped_rows.length > 0 && (
            <Table
              style={{ marginTop: 14 }}
              size="small"
              rowKey="row_number"
              pagination={false}
              dataSource={commitResult.skipped_rows}
              columns={[
                {
                  title: '行号',
                  dataIndex: 'row_number',
                  width: 100,
                  render: (v: number) => <span className="mono">{v}</span>,
                },
                { title: '原因', dataIndex: 'reason' },
              ]}
            />
          )}

          <div className="action-bar">
            <span className="action-bar-note">该批次已锁定，重复提交会被拒绝（409）</span>
            <Button onClick={resetAll}>继续导入其他文件</Button>
          </div>
        </Panel>
      )}

      <Panel title="中断恢复" sub="页面刷新或网络中断后使用">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <InputNumber
            min={1}
            placeholder="批次号"
            style={{ width: 150 }}
            value={restoreId ?? undefined}
            onChange={(value) => setRestoreId(typeof value === 'number' ? value : null)}
          />
          <Button icon={<ReloadOutlined />} onClick={() => void handleRestore()} loading={busy === 'validate'}>
            按批次号恢复
          </Button>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            已提交的批次不会被重复写入
          </Typography.Text>
        </div>
      </Panel>
    </>
  );
}
