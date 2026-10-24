import { Button, Descriptions, Drawer, Empty, Tag } from 'antd';
import type { DemoChange, DemoStudent, Tone } from '../demo/types';

const TONE_COLOR: Record<Tone, string> = {
  success: 'green',
  info: 'blue',
  warning: 'orange',
  danger: 'red',
  muted: 'default',
};

interface StudentProfileDrawerProps {
  student: DemoStudent | null;
  changes: DemoChange[];
  open: boolean;
  onClose: () => void;
  onOpenChanges: (uid: string) => void;
  onLocateChange: (changeNo: string) => void;
}

/**
 * 学生档案抽屉：工作台和辅导员台共用。
 * 定位动作只接受服务端已确认的 UID/异动编号，页面本身仍从当前身份的数据范围取数。
 */
export default function StudentProfileDrawer({
  student,
  changes,
  open,
  onClose,
  onOpenChanges,
  onLocateChange,
}: StudentProfileDrawerProps) {
  const ordered = [...changes].sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));

  return (
    <Drawer
      title={student ? `${student.uid} · ${student.name}` : '学生档案'}
      open={open}
      onClose={onClose}
      width={620}
      destroyOnClose
      extra={
        student ? (
          <Button size="small" onClick={() => onOpenChanges(student.uid)}>
            在异动台账中定位
          </Button>
        ) : null
      }
    >
      {student ? (
        <div className="wb-drawer">
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="UID">{student.uid}</Descriptions.Item>
            <Descriptions.Item label="姓名（脱敏）">{student.name}</Descriptions.Item>
            <Descriptions.Item label="性别">{student.gender || '—'}</Descriptions.Item>
            <Descriptions.Item label="学院 / 专业">{student.college} / {student.major}</Descriptions.Item>
            <Descriptions.Item label="班级">{student.class_name}</Descriptions.Item>
            <Descriptions.Item label="年级 / 入学年份">{student.grade} / {student.enrollment_year ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="学籍状态">
              <Tag color={TONE_COLOR[student.status_tone]}>{student.status}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="辅导员">{student.counselor}</Descriptions.Item>
            <Descriptions.Item label="本人电话">{student.phone}</Descriptions.Item>
            <Descriptions.Item label="身份证">{student.id_card}</Descriptions.Item>
            <Descriptions.Item label="生源地">{student.source_region || '—'}</Descriptions.Item>
            <Descriptions.Item label="数据标记">
              {student.flags.length ? student.flags.join('、') : '无'}
            </Descriptions.Item>
          </Descriptions>

          <h3 className="wb-drawer-title">学籍异动记录</h3>
          {ordered.length ? (
            <div className="wb-change-list">
              {ordered.map((item) => (
                <div className="wb-change" key={item.change_no}>
                  <div className="wb-change-top">
                    <b>{item.type}</b>
                    <span>{item.date}</span>
                    <Tag color={item.status.includes('已批') ? 'green' : 'orange'}>{item.status}</Tag>
                  </div>
                  <p>{item.reason || '未填原因'}</p>
                  {item.target ? <small>去向：{item.target}</small> : null}
                  <Button
                    size="small"
                    type="link"
                    className="wb-change-locate"
                    aria-label={`在台账中定位异动 ${item.change_no}`}
                    onClick={() => onLocateChange(item.change_no)}
                  >
                    在台账中定位
                  </Button>
                </div>
              ))}
            </div>
          ) : (
            <Empty description="暂无学籍异动" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}
          <p className="wb-note">
            原始学号、完整身份证与电话不在演示页面展示；UID 映射保存在本地数据管理员侧。
          </p>
          <p className="wb-note">
            定位链接只携带当前身份可读的 UID 或异动编号，跨范围访问会被页面数据范围拒绝。
          </p>
        </div>
      ) : null}
    </Drawer>
  );
}
