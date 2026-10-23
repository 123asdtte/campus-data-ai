import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import BrandMark from './BrandMark';
import { EmptyState, PageHeader, Panel, StatTile, StatusBadge } from './ui';

describe('StatusBadge', () => {
  it('按 tone 渲染状态类名与文字', () => {
    const { container } = render(<StatusBadge tone="warning" label="待处理" />);
    const badge = container.querySelector('.status');

    expect(badge).not.toBeNull();
    expect(badge?.classList.contains('is-warning')).toBe(true);
    expect(badge?.textContent).toContain('待处理');
  });

  it('muted 使用无修饰的基础状态类', () => {
    const { container } = render(<StatusBadge tone="muted" label="未知" />);
    const badge = container.querySelector('.status');

    expect(badge?.className).toBe('status');
  });
});

describe('PageHeader', () => {
  it('渲染标题、描述与操作区', () => {
    render(
      <PageHeader
        title="学生信息"
        description="按学院与状态筛选"
        extra={<button type="button">导出</button>}
      />,
    );

    expect(screen.getByRole('heading', { name: '学生信息' })).toBeTruthy();
    expect(screen.getByText('按学院与状态筛选')).toBeTruthy();
    expect(screen.getByRole('button', { name: '导出' })).toBeTruthy();
  });
});

describe('StatTile / Panel / EmptyState', () => {
  it('渲染统计块与面板内容', () => {
    render(
      <Panel title="导入概览" sub="最近 6 个月">
        <StatTile label="学生总数" value={235} hint="虚构数据" />
      </Panel>,
    );

    expect(screen.getByText('导入概览')).toBeTruthy();
    expect(screen.getByText('最近 6 个月')).toBeTruthy();
    expect(screen.getByText('学生总数')).toBeTruthy();
    expect(screen.getByText('235')).toBeTruthy();
  });

  it('空状态显示标题与提示', () => {
    render(<EmptyState title="暂无异常" hint="导入后会在这里显示" />);

    expect(screen.getByText('暂无异常')).toBeTruthy();
    expect(screen.getByText('导入后会在这里显示')).toBeTruthy();
  });
});

describe('BrandMark', () => {
  it('默认 24px，支持自定义尺寸', () => {
    const { container, rerender } = render(<BrandMark />);
    const svg = container.querySelector('svg');

    expect(svg).not.toBeNull();
    expect(svg?.getAttribute('width')).toBe('24');
    expect(svg?.getAttribute('aria-hidden')).toBe('true');

    rerender(<BrandMark size={16} />);
    expect(container.querySelector('svg')?.getAttribute('width')).toBe('16');
  });
});
